"""One preregistered fresh-process active-coverage batch, with full readback timing."""

import argparse
from fractions import Fraction
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = HERE.parent / 'm4_active_coverage_001'
ORDER = ('SCENE', 'TOP', 'LEFT', 'RIGHT', 'FRONT', 'BACK')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode('utf8')


def save(path, value):
    path.write_bytes(encode(value))


def source_files():
    paths = [HERE / name for name in ('runner.py', 'runtime.py', 'validate.py', 'PREREGISTRATION.json')]
    paths.extend(sorted((HERE / 'inputs').glob('*.json')))
    paths.extend((BASE / 'coverage.py', BASE / 'render/adapter.py', BASE / 'CONTENT_MANIFEST.json'))
    dependencies = json.loads((HERE / 'inputs/DEPENDENCIES.json').read_bytes())
    paths.extend(Path(name) for name in dependencies['installed_sources_sha256'])
    paths.append(ROOT / 'verification/m4_surface_scan_compact_facts_001/installation/run_01/FIXED_BUILD_INPUTS.json')
    paths.append(Path(sys.executable))
    return sorted(set(path.resolve() for path in paths))


def hashes(paths):
    return {str(path): sha(path.read_bytes()) for path in paths}


def reference_hashes():
    manifest = json.loads((BASE / 'CONTENT_MANIFEST.json').read_bytes())
    by_path = {row['path']: row['sha256'] for row in manifest['files']}
    paths = [BASE / 'render' / (view + suffix) for view in ORDER for suffix in ('.png', '.npz', '.json')]
    return {str(path.resolve()): by_path[path.relative_to(ROOT).as_posix()] for path in paths}


def environment():
    return {'python': sys.version, 'executable': sys.executable,
            'numpy_version': importlib.metadata.version('numpy'),
            'Pillow_version': importlib.metadata.version('Pillow')}


def verify_frozen(frozen):
    if hashes(source_files()) != frozen['runtime_sources']:
        raise ValueError('runtime_source_or_input_changed')
    if reference_hashes() != frozen['parent_post_run_reference_only']:
        raise ValueError('parent_post_run_reference_changed')
    if environment() != frozen['environment']:
        raise ValueError('runtime_library_or_python_identity_changed')


def load_validator():
    # Parent-side libraries are common setup. Each child still imports its own.
    import numpy
    import PIL.Image
    spec = importlib.util.spec_from_file_location('_active002_validator', HERE / 'validate.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def ratio_record(value):
    return {'numerator': value.numerator, 'denominator': value.denominator, 'value': float(value)}


def same_coverage(a, b):
    keys = ('roi_ids', 'covered_roi_ids', 'candidate_pool_uncovered_roi_ids',
            'scene_identity', 'candidate_identity')
    return all(a[key] == b[key] for key in keys)


def summarize(rows, controls):
    counts = {name: sum(row['status'] == name for row in rows) for name in ('completed', 'failed', 'not_run')}
    complete = counts['completed'] == 12
    result = {'main_planned_runs': 12, 'main_counts': counts,
              'control_planned_runs': 2,
              'control_counts': {name: sum(row['status'] == name for row in controls)
                                 for name in ('completed', 'failed', 'not_run')},
              'main_workload_qualified': complete, 'net_time_benefit': None}
    if complete:
        pairs = []
        for number in range(1, 7):
            a, b = [next(row for row in rows if row['pair'] == number and row['arm'] == arm) for arm in ('A', 'B')]
            pairs.append({'pair': number, 'A_ns': a['elapsed_ns'], 'B_ns': b['elapsed_ns'],
                          'B_over_A': ratio_record(Fraction(b['elapsed_ns'], a['elapsed_ns']))})
        med_a = statistics.median(Fraction(row['elapsed_ns']) for row in rows if row['arm'] == 'A')
        med_b = statistics.median(Fraction(row['elapsed_ns']) for row in rows if row['arm'] == 'B')
        paired = statistics.median(Fraction(row['B_ns'], row['A_ns']) for row in pairs)
        result.update(pairs=pairs, A_median_ns=ratio_record(med_a), B_median_ns=ratio_record(med_b),
                      median_pair_ratio=ratio_record(paired), ratio_of_medians=ratio_record(med_b / med_a),
                      net_time_benefit=paired < 1,
                      conclusion='observed_net_time_benefit' if paired < 1 else 'fewer_calls_total_time_not_won')
    control_passed = all(row['status'] == 'completed' for row in controls)
    result['control_qualified'] = control_passed
    result['author_engineering_gate'] = complete and control_passed
    result['full_cost_gate'] = result['author_engineering_gate'] and result['net_time_benefit'] is True
    return result


def execute_one(row, validator, prereg):
    folder = HERE / 'runs' / row['id']
    folder.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, '-I', '-B', '-X', 'utf8', str(HERE / 'runtime.py'),
               '--arm', row['arm'], '--scenario', row['scenario'], '--output', str(folder),
               '--trace', str(folder / 'TRACE.jsonl')]
    process = None
    try:
        with (folder / 'STDOUT.bin').open('xb') as out, (folder / 'STDERR.bin').open('xb') as err:
            started = time.perf_counter_ns()
            row['started_ns'] = started
            try:
                process = subprocess.Popen(command, cwd=folder, stdin=subprocess.DEVNULL, stdout=out, stderr=err)
                row['process_id'] = process.pid
                process.wait(timeout=prereg['limits']['per_process_timeout_seconds'])
                row['process_exited_ns'] = time.perf_counter_ns()
                row['returncode'] = process.returncode
            finally:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
                    row['cleanup_exited_ns'] = time.perf_counter_ns()
        stdout = (folder / 'STDOUT.bin').read_bytes()
        stderr = (folder / 'STDERR.bin').read_bytes()
        row['stdout_bytes'], row['stderr_bytes'] = len(stdout), len(stderr)
        row['stdout_sha256'], row['stderr_sha256'] = sha(stdout), sha(stderr)
        row['render_attempts'] = validator.read_attempts(folder)
        if row['returncode'] != 0:
            raise ValueError('child_returned_failure')
        facts = validator.validate_run(folder, row['arm'], row['scenario'])
        raw_result = json.loads((folder / 'RESULT.json').read_bytes())
        if raw_result['process_id'] != row['process_id'] or Path(raw_result['output_directory']).resolve() != folder.resolve():
            raise ValueError('child_process_or_output_binding')
        if not started <= raw_result['started_ns'] <= raw_result['work_closed_ns'] <= time.perf_counter_ns():
            raise ValueError('child_monotonic_window_outside_parent')
        if facts['render_attempts'] != row['render_attempts']:
            raise ValueError('trace_and_result_attempts_differ')
        row.update(status='completed', facts=facts)
    except BaseException as error:
        row.update(status='failed', error={'type': type(error).__name__, 'message': str(error),
                                          'traceback': traceback.format_exc()})
        try:
            row['render_attempts'] = validator.read_attempts(folder)
        except BaseException as trace_error:
            row['render_attempts'] = None
            row['render_attempts_lower_bound'] = getattr(trace_error, 'known_attempts', 0)
            row['attempt_count_error'] = str(trace_error)
    finally:
        row['closed_ns'] = time.perf_counter_ns()
        row['elapsed_ns'] = row['closed_ns'] - row['started_ns'] if 'started_ns' in row else None
        row['output_directory'] = str(folder)


def run(frozen):
    batch_started = time.perf_counter_ns()
    verify_frozen(frozen)
    with (HERE / 'BATCH_STARTED.json').open('x', encoding='utf8') as stream:
        json.dump({'started_ns': time.perf_counter_ns(), 'freeze_sha256': sha((HERE / 'FROZEN.json').read_bytes()),
                   'scope': 'Exclusive reservation for all 12 main and two separately accounted control slots.'}, stream)
    setup_started = time.perf_counter_ns()
    validator = load_validator()
    prereg = json.loads((HERE / 'PREREGISTRATION.json').read_bytes())
    rows = [dict(row, status='not_run') for row in prereg['main']]
    controls = [dict(row, status='not_run') for row in prereg['control']]
    setup_closed = time.perf_counter_ns()
    stop = None
    for row in rows + controls:
        try:
            verify_frozen(frozen)
            execute_one(row, validator, prereg)
            if row['status'] != 'completed':
                raise ValueError('scheduled_run_failed')
            previous = [other for other in rows + controls if other is not row and other['status'] == 'completed'
                        and other['scenario'] == row['scenario'] and other['pair'] == row['pair']]
            if previous and not same_coverage(previous[0]['facts'], row['facts']):
                row['status'] = 'failed'
                raise ValueError('paired_actual_coverage_mismatch')
            attempted = sum(other.get('render_attempts') or 0 for other in rows + controls)
            limit = prereg['limits']['main_render_attempts'] if row['scenario'] == 'main' else prereg['limits']['all_render_attempts_including_preparation_and_failures']
            if attempted > limit:
                row['status'] = 'failed'
                raise ValueError('actual_render_attempt_cap_exceeded')
            verify_frozen(frozen)
        except BaseException as error:
            stop = {'run_id': row['id'], 'type': type(error).__name__, 'message': str(error)}
        save(HERE / 'PROGRESS.json', {'rows': rows, 'controls': controls, 'stop': stop})
        if stop:
            break
    summary = summarize(rows, controls)
    if stop:
        summary['author_engineering_gate'] = False
        summary['full_cost_gate'] = False
    for label, slots in (('main', rows), ('control', controls)):
        entered = [row for row in slots if row['status'] != 'not_run']
        complete_counts = all(row.get('render_attempts') is not None for row in entered)
        known = sum(row.get('render_attempts') or row.get('render_attempts_lower_bound', 0) for row in entered)
        summary[label + '_render_attempts'] = known if complete_counts else None
        summary[label + '_known_render_attempts_lower_bound'] = known
    summary['attempt_count_complete'] = all(row.get('render_attempts') is not None for row in rows + controls if row['status'] != 'not_run')
    closed = time.perf_counter_ns()
    result = {'cycle': 'M4-ACTIVE-COVERAGE-002', 'rows': rows, 'controls': controls, 'stop': stop,
              'summary': summary, 'freeze_sha256': sha((HERE / 'FROZEN.json').read_bytes()),
              'batch_started_ns': batch_started, 'batch_closed_before_publication_ns': closed,
              'whole_batch_through_analysis_ns': closed - batch_started,
              'common_parent_setup': {'started_ns': setup_started, 'closed_ns': setup_closed, 'elapsed_ns': setup_closed-setup_started},
              'timing_scope': prereg['time_contract'], 'preparation_render_attempts': 0,
              'new_experimental_model_provider_Blender_API_runs': 0, 'administrator_review': 'pending',
              'controller_bootstrap_scope': 'Whole batch starts at run() entry before first integrity/reservation. Controller process startup, standard-library imports and initial FROZEN JSON read are unmeasured. Primary per-child timing includes that child startup and all imports.'}
    save(HERE / 'RESULTS.json', result)
    print(json.dumps(summary, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', action='store_true')
    parser.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.freeze == args.run:
        parser.error('choose one mode')
    if args.freeze:
        path = HERE / 'FROZEN.json'
        data = {'cycle': 'M4-ACTIVE-COVERAGE-002', 'runtime_sources': hashes(source_files()),
                'parent_post_run_reference_only': reference_hashes(), 'environment': environment(),
                'scope': 'Child runtime never reads the separate parent post-run reference image set.'}
        with path.open('xb') as stream:
            stream.write(encode(data))
        print('frozen_without_any_child_or_render_execution')
        return
    run(json.loads((HERE / 'FROZEN.json').read_bytes()))


if __name__ == '__main__':
    main()
