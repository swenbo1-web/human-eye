"""One actual installed typed-worker correctness episode; no performance sample."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback
import unittest


HERE = Path(__file__).resolve().parent
CORRECTNESS = HERE.parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main():
    ready_path = CORRECTNESS.parent / 'installation/READY.json'
    inventory_path = CORRECTNESS.parent / 'measurement/assets_01/INPUTS.json'
    ready = json.loads(ready_path.read_bytes())
    asset = next(row for row in json.loads(inventory_path.read_bytes())['inputs'] if row['name'] == 'simple_boxes')
    asset_path = Path(asset['asset'])
    entry_path = Path(ready['entry'])
    binding_path = entry_path.with_name('RUNTIME_BINDING.json')
    binding = json.loads(binding_path.read_bytes())
    engine = Path(ready['install_root'])
    pinned_paths = [Path(__file__), CORRECTNESS / 'oracle.py', ready_path, inventory_path,
        asset_path, entry_path, binding_path, entry_path.with_name('installed_release.py'),
        ROOT / 'verification/m1_task_entry_001_eval/preflight_client.py']
    pinned_paths.extend(engine / row['path'] for row in binding['source_files'])
    pins = {str(path): sha(path) for path in pinned_paths}
    save('INPUT_BINDINGS.json', {'source_files': pins, 'ready': ready,
        'oracle_scope': 'existing actual evaluated vertex export bound to the exact unchanged asset SHA; Fraction affine oracle, no new source export',
        'asset': asset, 'models': 0, 'performance_samples': 0, 'planned_owned_typed_workers': 1})
    check = unittest.TestCase()
    check.assertEqual(sha(asset_path), asset['asset_sha256'])
    check.assertEqual(ready['commit'], 'fac9b4373575d653cc96f39f1dcb225300cd5977')
    check.assertEqual(ready['source_sha256'], '6acb3ac7f014a590a279994f44be07c581af53a2da4dafae8dba9cd58eaea0bb')
    check.assertEqual(len(binding['source_files']), 137)
    bootstrap = load(entry_path, '_directory_typed_installed_bootstrap')
    proof = bootstrap.validate_binding(expected_python=sys.executable)
    sys.path.insert(0, proof['module_root'])
    identity, origins = bootstrap.verify_imported_runtime(proof)
    check.assertEqual(identity['source_kind'], 'installed_distribution')
    check.assertEqual(identity['source_sha256'], ready['source_sha256'])
    save('INSTALLED_IDENTITY.json', {'identity': identity, 'proof': proof, 'origins': origins})
    from human_eye_plugin.blender_process import BlenderProcessHost
    oracle = load(CORRECTNESS / 'oracle.py', '_directory_typed_independent_oracle')
    lifecycle = load(ROOT / 'verification/m1_task_entry_001_eval/preflight_client.py', '_directory_typed_lifecycle')
    raw_objects = [dict(row, name_full=row['name'], library_path='', unit_scale_m=asset['scale_length'])
        for row in asset['oracle']]
    source_sha = sha(engine / 'human_eye_plugin/blender_host.py')
    owned, handle = None, None
    requests, errors, forced_calls = [], [], []
    records = []
    closed = None
    started = time.perf_counter_ns()
    try:
        owned = BlenderProcessHost('D:/Tools/blender5.2/blender.exe', asset_path, timeout=30., startup_timeout=60.)
        capabilities = owned.capabilities()
        check.assertEqual(capabilities['process_id'], owned._process.pid)
        process_proof, handle = lifecycle._windows_runtime_proof(owned._process, capabilities['process_id'],
            time.perf_counter_ns() + 30_000_000_000)
        check.assertIs(process_proof['confirmed'], True)
        save('WORKER_IDENTITY.json', {'capabilities': capabilities, 'process_proof': process_proof,
            'argv': owned._process.args})
        request = owned._request

        def recorded_request(command, parameters, **kwargs):
            row = {'command': command, 'parameters': copy.deepcopy(parameters)}
            try:
                value = request(command, parameters, **kwargs)
                row['response'] = copy.deepcopy(value)
                return value
            except BaseException as exception:
                row['error'] = {'type': type(exception).__name__, 'message': str(exception)}
                raise
            finally:
                requests.append(row)

        owned._request = recorded_request
        for name in ('kill', 'terminate'):
            actual = getattr(owned._process, name)

            def tracked_close(*args, _actual=actual, _name=name, **kwargs):
                forced_calls.append(_name)
                return _actual(*args, **kwargs)

            setattr(owned._process, name, tracked_close)

        def directory(label):
            baseline = None if owned._scene_decoder is None else copy.deepcopy(owned._scene_decoder.baseline())
            packet = owned.capture_directory(time.perf_counter_ns() + 30_000_000_000, 2_000_000)
            oracle.assert_packet(check, packet, raw_objects, host_source_sha256=source_sha)
            exact_bounds = {oracle.existing_object_id(row['name_full']):
                oracle.tight_bounds(row['vertices_local'], row['matrix_world'], row['unit_scale_m'])
                for row in raw_objects}
            for row in packet['objects']:
                for field in ('bbox_min', 'bbox_max', 'center'):
                    check.assertEqual(row[field], exact_bounds[row['object_id']][field])
            check.assertEqual(packet['binding']['frame'], asset['frame'])
            check.assertEqual(packet['binding']['scale_length'], asset['scale_length'])
            check.assertEqual(packet['binding']['subframe'], 0.)
            check.assertEqual(None if owned._scene_decoder is None else owned._scene_decoder.baseline(), baseline)
            records.append({'label': label, 'packet': copy.deepcopy(packet), 'decoder_baseline_unchanged': True})
            save(label + '.json', packet)
            return packet

        cold = directory('directory_cold')
        hot = directory('directory_hot')
        check.assertIs(cold['cache_hit'], False)
        check.assertIs(hot['cache_hit'], True)
        check.assertEqual({key: value for key, value in cold.items() if key != 'cache_hit'},
                          {key: value for key, value in hot.items() if key != 'cache_hit'})
        check.assertIsNone(owned._scene_decoder)
        selected = owned.capture_task_scene([{'name': name} for name in asset['selected_names']])
        save('selected.json', selected)
        selected_baseline = copy.deepcopy(owned._scene_decoder.baseline())
        check.assertIsNotNone(selected_baseline)
        directory('directory_after_selected')
        check.assertEqual(owned._scene_decoder.baseline(), selected_baseline)
        complete = owned.capture_scene()
        save('full.json', complete)
        check.assertEqual(requests[-1]['command'], 'capture')
        check.assertEqual(requests[-1]['parameters']['_scene_baseline'], selected_baseline)
        check.assertEqual(len(complete['meshes']), asset['object_count'])
        check.assertEqual({row['name'] for row in complete['meshes']}, {row['name'] for row in raw_objects})
        full_baseline = copy.deepcopy(owned._scene_decoder.baseline())
        # Inspecting the current full baseline is local and performs no extra RPC.
        save('DELTA_BASELINES.json', {'selected': selected_baseline, 'full': full_baseline,
            'capture_request_used_unchanged_selected_baseline': True})
    except BaseException as exception:
        errors.append({'type': type(exception).__name__, 'message': str(exception), 'traceback': traceback.format_exc()})
    finally:
        if owned is not None:
            try:
                owned.close()
                closed = {'pid': owned._process.pid, 'exit_code': owned._process.poll(), 'reaped': owned._process.poll() is not None,
                    'closed': owned._closed, 'poisoned': owned._poisoned,
                    'reader_threads_stopped': not owned._stdout_thread.is_alive() and not owned._stderr_thread.is_alive(),
                    'forced_close_calls': forced_calls, 'runtime_exit': lifecycle._runtime_exit(handle),
                    'diagnostics': list(owned._diagnostics)}
                handle = None
            except BaseException as exception:
                errors.append({'stage': 'close', 'type': type(exception).__name__, 'message': str(exception)})
        if handle is not None:
            save('REMAINING_HANDLE_CLOSE.json', lifecycle._runtime_exit(handle))
        save('REQUESTS.json', requests)
        unchanged = all(sha(Path(path)) == expected for path, expected in pins.items())
        identity_after, _ = bootstrap.verify_imported_runtime(proof)
        normal_close = bool(closed and closed['exit_code'] == 0 and closed['reaped']
            and closed['closed'] and not closed['poisoned'] and closed['reader_threads_stopped']
            and not forced_calls and all(closed['runtime_exit'].get(key) is True for key in ('confirmed', 'exited', 'handle_closed'))
            and closed['runtime_exit'].get('exit_code') == 0)
        result = {'passed': not errors and unchanged and normal_close,
            'errors': errors, 'records': records, 'close': closed, 'source_files_unchanged': unchanged,
            'asset_unchanged': sha(asset_path) == asset['asset_sha256'],
            'identity_before': identity, 'identity_after': identity_after,
            'post_capabilities_requests': [row['command'] for row in requests],
            'owned_typed_workers': 1 if owned is not None else 0, 'performance_samples': 0,
            'model_consumers': 0, 'elapsed_ns': time.perf_counter_ns() - started,
            'oracle_scope': 'independent Fraction affine bounds of SHA-bound prior actual evaluated export, current file unchanged',
            'limitations': ['one fixed simple_boxes source, no freshness mutation or performance conclusion',
                'selected/full geometry methods retain their original contracts and may triangulate; directory response carries no arrays']}
        save('RESULTS.json', result)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
