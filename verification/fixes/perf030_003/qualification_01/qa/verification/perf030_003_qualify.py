"""Single 48-entry Stage A qualification for the fixed PERF-030-003 base.

Only standard-library code runs in this controller. Frozen 002 helpers own
snapshot export, same-byte worker bootstrap, publication records and cleanup.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
import types


ROOT = Path(__file__).resolve().parents[1]
BASE = '326b64c74b2672fd620ddb9cac83bf47dd5355f2'
BASE_SOURCE = '20fe8507cf3f802bd9471d2e8f7d00470f6013a6236f40e82258bd6aa6e7c5a0'
ORIGINAL_002_FREEZE = 'd17fb6b424aa2bca36f4c44ed7d5a9a5652ede253209b32ba97db7f7eb5db88d'
STATE_PATH = Path('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')
HELPER_PATH = 'verification/perf030_002_run.py'
WORKER_PATH = 'verification/perf030_003_worker.py'
RESULTS_PATH = 'verification/perf030_003_results.py'
INPUTS_PATH = 'verification/fixes/perf030_001/inputs.json'
ORIGINAL_FREEZE_PATH = 'verification/fixes/perf030_002/run_freeze.json'
CONTROLLER_PATH = 'verification/perf030_003_qualify.py'
CASE_IDS = (0, 1, 2, 3, 4, 5, 6, 11)
STATES = ('cold_measure', 'primed_hot_measure', 'cold_task')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError('PERF030_003 Stage A deadline exhausted')
    return seconds


def load_helpers(registration, deadline):
    row = next(item for item in registration['files'] if item['path'] == HELPER_PATH)
    completed = subprocess.run(['git', 'show', registration['qa_commit'] + ':' + HELPER_PATH],
        cwd=ROOT, capture_output=True, check=True, timeout=remaining(deadline))
    blob = completed.stdout
    if sha(blob) != row['sha256'] or len(blob) != row['bytes']:
        raise ValueError('frozen 002 controller helper differs')
    module = types.ModuleType('_perf030_003_frozen_002_controller')
    module.__file__ = str(ROOT / HELPER_PATH)
    sys.modules[module.__name__] = module
    exec(compile(blob, module.__file__, 'exec', dont_inherit=True), module.__dict__)
    module.WORKER_PATH = WORKER_PATH
    return module, blob


def main():
    started = time.monotonic()
    absolute_deadline = started + 300
    work_deadline = absolute_deadline - 5
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--window-token', required=True)
    args = parser.parse_args()
    state = json.loads(STATE_PATH.read_bytes())
    expected_window = {'owner': 'M3', 'cycle_id': 'PERF-030-003',
                       'status': 'granted', 'token': args.window_token}
    if any(state['performance_window'].get(name) != value for name, value in expected_window.items()):
        raise ValueError('PERF030_003 window grant does not match STATE')
    freeze_blob = args.freeze.read_bytes()
    registration = json.loads(freeze_blob)
    if registration['baseline_commit'] != BASE or registration['candidate_commit'] != BASE:
        raise ValueError('Stage A must use only the fixed 326 base')
    if registration['original_002_freeze_sha256'] != ORIGINAL_002_FREEZE:
        raise ValueError('002 lineage freeze differs')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError('Stage A output must stay in the M3 worktree')
    output.mkdir(parents=True, exist_ok=False)
    workers = []
    rows = []
    errors = []
    helper = None
    stats = None
    inputs = None
    completed = False
    summary = None
    costs = {'entry_costs': {'normal': defaultdict(int), 'diagnostic': defaultdict(int)},
             'record_publish_ns': 0, 'entries': 0}

    def hard_stop():
        for client in workers:
            try:
                if client.process.poll() is None:
                    client.process.kill()
            except OSError:
                pass
        os._exit(124)

    watchdog = threading.Timer(max(0, absolute_deadline - time.monotonic()), hard_stop)
    watchdog.daemon = True
    watchdog.start()
    try:
        stage_started = time.perf_counter_ns()
        helper, helper_blob = load_helpers(registration, work_deadline)
        costs['helper_fixed_load_ns'] = time.perf_counter_ns() - stage_started
        helper.save(output / 'registration.json', {'run_freeze_sha256': sha(freeze_blob),
            'run_freeze': registration, 'window_snapshot': state, 'phase': 'A',
            'case_indices': list(CASE_IDS), 'states': list(STATES),
            'order': 'case -> state -> normal then diagnostic', 'expected_entries': 48,
            'expected_prime_calls': 16, 'wall_budget_seconds': 300, 'cleanup_reserved_seconds': 5,
            'python': sys.version, 'executable': sys.executable})
        qa_root = output / 'qa'
        expected_files = {row['path']: row for row in registration['files']}
        if len(expected_files) != len(registration['files']):
            raise ValueError('duplicate frozen QA path')
        stage_started = time.perf_counter_ns()
        qa_sources = helper.export_files(registration['qa_commit'], expected_files,
            qa_root, work_deadline, expected_files)
        costs['qa_export_ns'] = time.perf_counter_ns() - stage_started
        for required in (HELPER_PATH, WORKER_PATH, RESULTS_PATH, INPUTS_PATH,
                         ORIGINAL_FREEZE_PATH, CONTROLLER_PATH):
            if required not in qa_sources:
                raise ValueError('Stage A QA manifest missing ' + required)
        if qa_sources[HELPER_PATH] != helper_blob:
            raise ValueError('helper bootstrap and QA archive differ')
        if sha(Path(__file__).read_bytes()) != sha(qa_sources[CONTROLLER_PATH]):
            raise ValueError('running Stage A controller differs from frozen QA')
        if sha(qa_sources[ORIGINAL_FREEZE_PATH]) != ORIGINAL_002_FREEZE:
            raise ValueError('frozen 002 lineage bytes differ')
        qa_manifest = {'commit': registration['qa_commit'], 'files': [
            {'path': name, 'sha256': sha(blob)} for name, blob in sorted(qa_sources.items())]}
        qa_manifest_path = output / 'qa_manifest.json'
        helper.save(qa_manifest_path, qa_manifest)
        inputs = json.loads(qa_sources[INPUTS_PATH])
        if len(inputs['cases']) != 12:
            raise ValueError('original input count differs')
        if inputs['cases'][5]['name'] != 'small_box' or inputs['cases'][6]['name'] != 'ring_probe':
            raise ValueError('qualification control cases differ')
        if inputs['cases'][11]['group'] != 'reject':
            raise ValueError('qualification reject control differs')
        stage_started = time.perf_counter_ns()
        stats = types.ModuleType('_perf030_003_fixed_results')
        stats.__file__ = str(qa_root / RESULTS_PATH)
        sys.modules[stats.__name__] = stats
        exec(compile(qa_sources[RESULTS_PATH], stats.__file__, 'exec', dont_inherit=True), stats.__dict__)
        costs['statistics_init_ns'] = time.perf_counter_ns() - stage_started
        runtime_root = output / 'runtime_baseline'
        stage_started = time.perf_counter_ns()
        manifest = helper.runtime_snapshot(BASE, runtime_root, work_deadline)
        costs['runtime_snapshot_export_ns'] = time.perf_counter_ns() - stage_started
        if manifest['source_sha256'] != BASE_SOURCE:
            raise ValueError('Stage A runtime source differs from fixed 326')
        runtime_manifest_path = output / 'baseline_runtime_manifest.json'
        helper.save(runtime_manifest_path, manifest)
        client = helper.Worker('baseline', runtime_root, qa_root, runtime_manifest_path,
            qa_manifest_path, sha(qa_sources[WORKER_PATH]), output, work_deadline)
        workers.append(client)
        client.wait_ready(work_deadline)
        costs['worker_start_ready_ns'] = client.start_ready_ns
        helper.save(output / 'baseline_ready.json', client.ready)
        if client.ready['identity']['runtime']['source_sha256'] != BASE_SOURCE:
            raise ValueError('executed Stage A runtime source differs')
        with (output / 'qualification_raw.jsonl').open('x', encoding='utf8') as raw:
            for case_index in CASE_IDS:
                case = inputs['cases'][case_index]
                for entry_state in STATES:
                    for diagnostic in (False, True):
                        remaining(work_deadline)
                        result, elapsed = client.request('qualify', 'stage-a-' + str(len(rows)),
                            work_deadline, case_index=case_index, state=entry_state, diagnostic=diagnostic)
                        row = {'case_index': case_index, 'case': case['name'], 'group': case['group'],
                            'state': entry_state, 'diagnostic': diagnostic, 'result': result,
                            'controller_roundtrip_ns': elapsed}
                        rows.append(row)
                        publication_started = time.perf_counter_ns()
                        raw.write(json.dumps(row, ensure_ascii=True, allow_nan=False) + '\n')
                        raw.flush()
                        costs['record_publish_ns'] += time.perf_counter_ns() - publication_started
                        costs['entries'] = len(rows)
                        kind = 'diagnostic' if diagnostic else 'normal'
                        for name, value in result['costs'].items():
                            if isinstance(value, int):
                                costs['entry_costs'][kind][name] += value
                        if result.get('exception'):
                            raise RuntimeError('qualification entry failed ' + json.dumps(result['exception']))
        if len(rows) != 48:
            raise ValueError('qualification entry count differs')
        prime_calls = sum(item['prime_calls'] for item in costs['entry_costs'].values())
        if prime_calls != 16:
            raise ValueError('qualification prime count differs ' + str(prime_calls))
        finished, _ = client.request('finish', 'stage-a-finish', work_deadline)
        helper.save(output / 'baseline_finished.json', finished)
        completed = True
    except BaseException as exc:
        errors.append({'type': type(exc).__name__, 'message': str(exc),
                       'traceback': traceback.format_exc(), 'entries_preserved': len(rows)})
    finally:
        cleanup_started = time.perf_counter_ns()
        for client in workers:
            if client.process.poll() is None:
                client.process.kill()
        for client in workers:
            try:
                client.close(absolute_deadline)
            except BaseException as exc:
                errors.append({'stage': 'cleanup', 'type': type(exc).__name__, 'message': str(exc)})
        costs['cleanup_ns'] = time.perf_counter_ns() - cleanup_started
        costs['worker_roundtrip_ns'] = {client.arm: dict(client.roundtrip_ns) for client in workers}
        costs['worker_stdout_publish_ns'] = {client.arm: client.stdout_publish_ns for client in workers}
        if helper is not None:
            if stats is not None and inputs is not None:
                try:
                    summary_started = time.perf_counter_ns()
                    summary = stats.summarize(rows, inputs)
                    helper.save(output / 'summary.json', summary)
                    costs['summary_and_publish_ns'] = time.perf_counter_ns() - summary_started
                except BaseException as exc:
                    errors.append({'stage': 'summary', 'type': type(exc).__name__, 'message': str(exc)})
            costs['total_wall_ns_before_seal'] = int((time.monotonic() - started) * 1e9)
            helper.save(output / 'errors.json', errors)
            helper.save(output / 'costs.json', costs)
            helper.save(output / 'run_status.json', {'phase': 'A', 'completed_protocol': completed,
                'entries': len(rows), 'entries_complete': len(rows) == 48,
                'qualification_supported': summary.get('qualification_supported') if summary is not None else None,
                'errors': len(errors), 'all_workers_reaped': all(client.process.poll() is not None for client in workers),
                'elapsed_seconds_before_status': time.monotonic() - started})
            helper.save(output / 'completion_timing.json', {
                'total_wall_ns_through_artifact_seal': int((time.monotonic() - started) * 1e9),
                'json_save_publications': list(helper.JSON_SAVE_LEDGER),
                'json_save_totals': {'files': len(helper.JSON_SAVE_LEDGER),
                    'bytes': sum(item['bytes'] for item in helper.JSON_SAVE_LEDGER),
                    'encode_write_flush_ns': sum(item['encode_write_flush_ns'] for item in helper.JSON_SAVE_LEDGER)},
                'terminal_timing_publication_excluded': True})
        else:
            # Bootstrap failures precede the reusable publication helper.
            with (output / 'bootstrap_error.json').open('x', encoding='utf8') as stream:
                json.dump({'errors': errors, 'elapsed_seconds': time.monotonic() - started}, stream, indent=2)
                stream.write('\n')
    watchdog.cancel()
    return 0 if completed and not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
