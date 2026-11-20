"""Replay sealed worker receipts through the recovery glue with no live launches."""

import argparse
import copy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch


NS = Path(__file__).resolve().parents[1]
V = NS.parent
HERE = NS / 'harness'
GENERIC = V / 'm4_global_local_qualification_001/harness/reused/owned_native.py'
OLD_FIXTURE = Path('D:/he_m4_cross_scale_live_task_001/fixture/main.blend')
OLD_FIXTURE_SHA = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
GENERIC_SHA = 'b1690d442b16ba2ddd20e08d46ae341aa4efe1caa0cc431487098ffa5c611c21'
WIRE_SHA = '8d3e486a4d4ad3a68e46f376c62c24a00ce472424d8d54d9e579247a96d9e5a9'
HISTORICAL = {
    'qualification': (Path('D:/he_m4_cross_scale_live_qualification_001'),
                      V / 'm4_cross_scale_live_qualification_001/RUNTIME_INDEX.json',
                      '174ed1015ce9b70e37ba8410e6f2e7d5a955f66e8d2ff5e76a381272819028c7'),
    'failed': (Path('D:/he_m4_cross_scale_live_task_001'),
               V / 'm4_cross_scale_live_task_001/RUNTIME_INDEX.json',
               '0244f3a3268912f9485003ea0c8e5814894e4c1daf30e04bec8ddb05ba287b79'),
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, name):
    if not condition:
        raise ValueError(name)


class Evidence:
    def __init__(self):
        self.pins = {}
        self.indexes = {}
        for name, (folder, index, digest) in HISTORICAL.items():
            manifest = self.read(index, digest)
            rows = {row['path']: row for row in manifest['files']}
            require(len(rows) == len(manifest['files']), 'duplicate_original_runtime_path')
            self.indexes[name] = (folder, rows)

    def pin(self, path, expected=None):
        path = Path(path).resolve(strict=True)
        digest = sha(path)
        require(expected is None or digest == expected, f'input_hash_differs/{path}')
        self.pins[str(path)] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest}
        return path

    def read(self, path, expected=None):
        return json.loads(self.pin(path, expected).read_bytes())

    def original(self, key, label, relative, *, as_json=True):
        folder, manifest = self.indexes[key]
        name = f'slots/{label}/{relative}'
        registered = manifest[name]
        path = (folder / name).resolve(strict=True)
        require(path.is_relative_to(folder.resolve()), 'unexpected_original_runtime_path')
        require(path.stat().st_size == registered['bytes'], 'original_runtime_length_mismatch')
        pinned = self.pin(path, registered['sha256'])
        return json.loads(pinned.read_bytes()) if as_json else pinned

    def original_path(self, key, label):
        folder, _ = self.indexes[key]
        return folder / 'slots' / label


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def ready_original(evidence):
    def original(relative, **kwargs):
        return evidence.original('qualification', 'Q1', relative, **kwargs)

    result = original('SLOT_RESULT.json')
    publication = original('SLOT_PUBLICATION.json')
    runtime = original('RUNTIME_CLOSE.json')
    ready = original('native/READY.json')
    worker = original('native/WORKER_CLOSED.json')
    spawn = original('native/SPAWN.json')
    config = original('native/CONFIG.json')
    retained = original('NATIVE_RUNTIME_PROOF.json')
    input_asset = original('native/input.blend', as_json=False)
    require(result['status'] == publication['status'] == 'completed', 'Q1_not_original_success')
    require(publication['result_sha256'] == sha(evidence.original_path('qualification', 'Q1') / 'SLOT_RESULT.json'),
            'Q1_published_result_hash_invalid')
    require(runtime['Blender_status']['ready'] == ready and runtime['Blender_status']['closed'] == worker,
            'Q1_aggregated_worker_receipts_do_not_match_raw')
    require(ready['pid'] == worker['pid'] == spawn['pid'] == runtime['Blender_close']['pid'],
            'Q1_worker_PID_mismatch')
    require('qa_vertex_patch' not in config and 'qa_patch_applied' not in worker and 'display_restored' not in worker,
            'Q1_not_the_unmodified_generic_READ_ONLY_contract')
    require(sha(input_asset) == config['asset_sha256'] == spawn['asset_sha256'], 'Q1_asset_copy_digest_mismatch')
    assets = {'original': evidence.pin(config['asset'], config['asset_sha256']), 'copy': input_asset}
    closure = {
        'errors': runtime['errors'],
        'Blender_close': runtime['Blender_close'],
        'Blender_status': runtime['Blender_status'],
        'Blender_exit': result['cleanup']['native_retained_exit'],
        'public_MCP_close': runtime['MCP_stdio_close'],
        'public_MCP_exit': runtime['MCP_retained_exit'],
    }
    return {'closure': closure, 'ready': ready, 'worker': worker, 'spawn': spawn, 'config': config,
            'retained': retained, 'asset_paths': assets, 'result': result}


def not_ready_original(evidence, label):
    def original(relative, **kwargs):
        return evidence.original('failed', label, relative, **kwargs)

    folder = evidence.original_path('failed', label)
    result = original('SLOT_RESULT.json')
    publication = original('SLOT_PUBLICATION.json')
    runtime = original('RUNTIME_CLOSE.json')
    spawn = original('native/SPAWN.json')
    failure = original('native/START_FAILURE.json')
    config = original('native/CONFIG.json')
    copied = original('native/input.blend', as_json=False)
    stderr = original('native/worker_stderr.txt', as_json=False)
    require(result['status'] == publication['status'] == 'failed', 'legacy_slot_not_original_failure')
    require(publication['result_sha256'] == sha(folder / 'SLOT_RESULT.json'), 'legacy_published_result_hash_invalid')
    require('visual004_native_display_fixed_mesh_inventory' in stderr.read_text(encoding='utf8') and
            failure['reason'] == 'visual004_native_worker_start_failed' and not (folder / 'native/READY.json').exists(),
            'legacy_failure_not_original_pre_READY_inventory_rejection')
    require('Blender_close' not in runtime and 'Blender_status' not in runtime,
            'legacy_failure_already_has_completed_session_fields')
    require(sha(copied) == config['asset_sha256'] == spawn['asset_sha256'] == OLD_FIXTURE_SHA,
            'legacy_owned_asset_copy_digest_mismatch')
    old_helper = Path(spawn['command'][spawn['command'].index('--python') + 1])
    evidence.pin(old_helper, spawn['helper_sha256'])
    starters = [row for row in result['budget']['records'] if row['claim']['kind'] == 'Blender_start'
                and row['claim']['label'] == label]
    require(len(starters) == 1 and starters[0]['settlement']['pid'] == spawn['pid']
            and starters[0]['settlement']['outcome'] == 'failed', 'legacy_failure_budget_binding')
    row = starters[0]
    token = row['claim']['token']
    parent = folder.parents[1] / 'budget'
    settlement = evidence.read(parent / 'settlements' / (token + '.json'))
    require(settlement == row['settlement'], 'legacy_original_ledger_settlement_mismatch')
    return {'folder': folder, 'result': result, 'closure': runtime, 'spawn': spawn, 'failure': failure,
            'config': config, 'asset_paths': {'original': OLD_FIXTURE, 'copy': copied}, 'ledger_row': row}


def check_start(runtime, worker, evidence, output):
    signature = inspect.signature(worker.NativeSession.start)
    require(signature.parameters['qa_vertex_patch'].default is None
            and 'display_steps_enabled' not in signature.parameters, 'generic_worker_signature_changed')
    require(Path(inspect.getsourcefile(worker.NativeSession.start)).resolve() == GENERIC.resolve(),
            'unexpected_native_start_implementation')
    checks = []
    for condition in ('N', 'P'):
        calls = []
        expected = dict(blender=runtime.BLENDER, asset=OLD_FIXTURE,
                        workspace=output.parent / f'mocked-{condition}' / 'native',
                        deadline_ns=time.perf_counter_ns() + 600_000_000_000,
                        condition=condition, expected_asset_sha256=OLD_FIXTURE_SHA)
        sentinel = object()

        def fake_start(**kwargs):
            signature.bind(**kwargs)
            calls.append(kwargs)
            return sentinel

        with patch.object(worker.NativeSession, 'start', side_effect=fake_start) as mock:
            output_identity = runtime.start_generic_native(worker.NativeSession.start, **expected)
        require(mock.call_count == 1 and calls == [{**expected, 'max_calls': 48}]
                and output_identity is sentinel, 'actual_runtime_did_not_call_generic_worker_exactly_once')
        require(set(calls[0]) == set(expected) | {'max_calls'}, 'optional_worker_controls_were_passed')
        checks.append({'condition': condition, 'call_count': mock.call_count,
                       'actual_forwarded_arguments': {k: str(v) if isinstance(v, Path) else v
                                                     for k, v in calls[0].items()},
                       'actual_generic_callable_from': str(evidence.pin(GENERIC, GENERIC_SHA)),
                       'generic_worker_default_QA_patch': None, 'spawned_processes': 0})
    return checks


def check_observed_launcher(runtime, worker, validator, output):
    """Exercise the actual wrapper and generic class with an inert Popen boundary."""
    outcomes = []
    for case, code in (('READY_received', None), ('pre_READY_worker_exit', 17), ('no_created_process', 0)):
        fake_runtime = SimpleNamespace(folder=output.parent / case, group='N',
            owned_deadline=time.perf_counter_ns() + 600_000_000_000,
            native_start_entered=False, startup_cleanup=None)
        commands = []

        def fake_popen(command, **settings):
            commands.append(command)
            require(settings['shell'] is False and '--disable-autoexec' in command,
                    'generic_inert_launcher_received_wrong_process_settings')
            if case == 'no_created_process':
                raise OSError('inert_Popen_control_without_a_process')
            config_path = Path(command[-1])
            config = json.loads(config_path.read_bytes())
            require(Path(command[command.index('--python') + 1]).resolve() == GENERIC.resolve()
                    and not {'qa_vertex_patch', 'display_steps_enabled'} & set(config),
                    'generic_inert_launcher_has_old_role_specific_options')
            if case == 'READY_received':
                ready = {'host': '127.0.0.1', 'port': 34567, 'pid': 987001,
                         'deadline_ns': config['deadline_ns'], 'initial_fingerprint': '1' * 64,
                         'helper_sha256': config['helper_sha256']}
                worker.publish_ready(config_path.parent / 'READY.json', ready, deadline_ns=config['deadline_ns'])
            return SimpleNamespace(pid=987001, poll=lambda: code)

        failure_type = None
        with patch('subprocess.Popen', side_effect=fake_popen) as mocked:
            try:
                session = runtime.Runtime.launch_native(fake_runtime, worker, OLD_FIXTURE, OLD_FIXTURE_SHA)
            except (OSError, ValueError) as error:
                failure_type = type(error).__name__
            require(mocked.call_count == 1 and len(commands) == 1 and fake_runtime.native_start_entered,
                    'generic_launcher_missing_or_duplicate_attempt')
        native = fake_runtime.folder / 'native'
        if case == 'READY_received':
            require(failure_type is None and fake_runtime.startup_cleanup is None and session.ready['pid'] == 987001
                    and (native / 'READY.json').is_file() and (native / 'SESSION.json').is_file(),
                    'mocked_generic_READY_not_preserved')
            outcomes.append({'case': case, 'status': 'ready', 'no_live_process': True})
            continue
        cleanup = fake_runtime.startup_cleanup
        failure = json.loads((native / 'START_FAILURE.json').read_bytes())
        require(failure_type == ('ValueError' if code else 'OSError') and cleanup['no_process_created'] is (code == 0)
                and cleanup['exit_code'] == (17 if code else None), 'mocked_generic_cleanup_observation_missing')
        spawned = native / 'SPAWN.json'
        spawn = json.loads(spawned.read_bytes()) if spawned.is_file() else None
        settlement = {'pid': cleanup['pid'], 'spawn_status': 'spawned' if spawn else 'not_spawned', 'outcome': 'failed'}
        verdict = validator.startup_closure(spawn=spawn, failure=failure, launch_cleanup=cleanup,
                                           settlement=settlement, asset_matches=sha(OLD_FIXTURE) == OLD_FIXTURE_SHA,
                                           copy_matches=sha(native / 'input.blend') == OLD_FIXTURE_SHA)
        require(verdict['passed'] is True and not (native / 'READY.json').exists(), 'mocked_PRE_READY_cleanup_unknown')
        outcomes.append({'case': case, 'no_live_process': True, 'failure_type': failure_type, 'validation': verdict})
    return outcomes


def check_close(validator, evidence):
    original = ready_original(evidence)
    success = validator.ready_closure(original['closure'], 'P', original['retained'])
    require(isinstance(success, dict) and success.get('passed', True) is True,
            'generic_ready_success_not_recognized')
    checks = [{'case': 'historical_generic_READY_complete_Q1', 'qualified_close': True,
               'projection': {'MCP_stdio_close': 'public_MCP_close', 'MCP_retained_exit': 'public_MCP_exit',
                              'SLOT_RESULT.cleanup.native_retained_exit': 'Blender_exit'},
               'validation': success, 'native_pid': original['ready']['pid']}]
    failed = [not_ready_original(evidence, label) for label in ('QN', 'QP')]
    for row in failed:
        args = {'spawn': row['spawn'], 'failure': row['failure'], 'launch_cleanup': None,
                'settlement': row['ledger_row']['settlement'],
                'asset_matches': sha(row['asset_paths']['original']) == OLD_FIXTURE_SHA,
                'copy_matches': sha(row['asset_paths']['copy']) == OLD_FIXTURE_SHA, 'ready': None}
        replay = validator.startup_closure(**args)
        require(replay['status'] == 'startup_failed_clean' and replay['passed'] is True,
                'historical_startup_failure_not_cleanly_classified')
        checks.append({'case': 'original_PRE_READY_failure_' + row['result']['label'],
                       'qualified_close': False, 'native_pid': row['spawn']['pid'], 'validation': replay,
                       'scope': 'Original launcher startup cleanup receipt and settled PID; no retained-handle observation.'})
    first = failed[0]
    common = {'spawn': first['spawn'], 'failure': first['failure'], 'launch_cleanup': None,
              'settlement': first['ledger_row']['settlement'], 'asset_matches': True,
              'copy_matches': True, 'ready': None}
    missing = validator.startup_closure(**{**common, 'settlement': None})
    require(missing['passed'] is None and missing['status'] == 'startup_cleanup_unknown',
            'missing_startup_settlement_promoted_to_success')
    checks.append({'case': 'startup_missing_settlement_negative', 'validation': missing})
    known_bad = validator.startup_closure(**{**common,
        'failure': {**first['failure'], 'cleanup_errors': [{'type': 'TimeoutError', 'reason': 'bounded replay control'}]}})
    require(known_bad['passed'] is False and known_bad['status'] == 'startup_cleanup_failed',
            'known_startup_cleanup_error_not_preserved')
    checks.append({'case': 'startup_cleanup_error_negative', 'validation': known_bad})
    wrong_asset = validator.startup_closure(**{**common, 'copy_matches': False})
    require(wrong_asset['passed'] is False, 'wrong_copied_asset_promoted_to_success')
    checks.append({'case': 'startup_copy_digest_mismatch_negative', 'validation': wrong_asset})

    aborted = copy.deepcopy(original['closure'])
    aborted['Blender_close'].update(exit_code=1, error={'type': 'ConnectionError', 'reason': 'synthetic post-READY error'})
    aborted['Blender_exit']['exit_code'] = 1
    aborted['Blender_status']['closed'] = None
    bad_cleanup = copy.deepcopy(original['closure'])
    bad_cleanup['Blender_exit'].update(confirmed=None, exited=None, handle_closed=None)
    changed = copy.deepcopy(original['closure'])
    changed['Blender_status']['closed']['final_geometry_fingerprint'] = '0' * 64
    qa = copy.deepcopy(original['closure'])
    qa['Blender_status']['closed']['qa_patch_applied'] = True
    for name, values in (('READY_process_exited_without_worker_close', aborted),
                         ('READY_retained_exit_unknown', bad_cleanup), ('READY_geometry_changed', changed),
                         ('READY_forbidden_QA_patch_applied', qa)):
        try:
            validator.ready_closure(values, 'P', original['retained'])
        except ValueError as error:
            checks.append({'case': name, 'qualified_close': False, 'validation_error': str(error),
                           'control_derived_from_bound_Q1': True})
        else:
            raise ValueError('malformed_or_abnormal_ready_close_promoted/' + name)
    return checks


def run(output):
    if not sys.flags.isolated or not sys.dont_write_bytecode:
        raise ValueError('pinned_isolated_interpreter_required')
    started = time.perf_counter_ns()
    evidence = Evidence()
    evidence.pin(Path(__file__))
    evidence.pin(sys.executable)
    evidence.pin(OLD_FIXTURE, OLD_FIXTURE_SHA)
    evidence.pin(GENERIC, GENERIC_SHA)
    evidence.pin(GENERIC.with_name('wire_meter.py'), WIRE_SHA)
    sys.path.insert(0, str(HERE))
    # Any unmocked attempt to launch a child in the actual imported paths is a test failure.
    with patch('subprocess.Popen', side_effect=AssertionError('offline replay must not start processes')) as spawn:
        runtime = load_module('_cross_recovery_receipt_runtime', evidence.pin(HERE / 'runtime.py'))
        validator = load_module('_cross_recovery_receipt_closure', evidence.pin(HERE / 'closure.py'))
        worker = load_module('_cross_recovery_receipt_worker', GENERIC)
        startup = check_start(runtime, worker, evidence, output)
        observed_launcher = check_observed_launcher(runtime, worker, validator, output)
        closures = check_close(validator, evidence)
        gone = spawn.call_count
    require(gone == 0, 'offline_replay_process_launch_attempted')
    for path in list(evidence.pins):
        require(sha(path) == evidence.pins[path]['sha256'], 'source_or_original_changed_during_replay')
    datum = {'passed': True, 'started_ns': started, 'finished_ns': time.perf_counter_ns(),
             'startup_calls': startup, 'inert_generic_launcher_controls': observed_launcher, 'closure_controls': closures,
             'historical_receipt_count': 3, 'Blender_launches': 0, 'model_launches': 0,
             'product_requests': 0, 'raster_attempts': 0,
             'source_pins': sorted(evidence.pins.values(), key=lambda row: row['path'])}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(datum, stream, indent=2, sort_keys=True)
        stream.write('\n')
    print(json.dumps({'passed': True, 'path': str(output), 'sha256': sha(output),
                      'startup_calls': len(startup), 'closure_controls': len(closures)}))


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('output', type=Path)
    run(cli.parse_args().output)
