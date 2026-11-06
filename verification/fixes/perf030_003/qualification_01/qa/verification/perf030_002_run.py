"""One bounded, fixed-source PERF-030-002 run after its CPU window is granted.

This controller imports only the standard library. Product execution happens
in two persistent workers compiled from the frozen QA bytes.
"""
from __future__ import annotations

import argparse
import ast
from collections import defaultdict
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import queue
import subprocess
import sys
import tarfile
import threading
import time
import traceback
import types


ROOT = Path(__file__).resolve().parents[1]
STATE = Path('D:/hefe/verification/fixes/20261106_parallel_coordination/STATE.json')
BASELINE = '11c8fc7332e530ead2f8fa30d2a35c7eb14e7d15'
CANDIDATE = '326b64c74b2672fd620ddb9cac83bf47dd5355f2'
BASELINE_SOURCE = 'e59048677b7cc05ac0f15b359e5444de2cc3ccc196994a701e74a2510f144163'
CANDIDATE_GEOMETRY = 'd3b47ed08de23bbf752b01f1ab2a7fe53b636cba5d4aa55621936e79837c384b'
ROOT_MODULES = (
    'human_eye_hook.py', 'human_eye_foveated_renderer.py',
    'native_3d_spatial_scratchpad.py', 'module_2_low_token_mcp_scene_bridge.py',
    'module_3_1_mcp_protocol_ipc_engine.py',
    'module_3_2_vlm_grounding_closed_loop_agent.py',
    'module_3_3_closed_loop_control_engine.py',
)
GEOMETRY_PATH = 'human_eye_plugin/geometry_safety.py'
STATIC_FREEZE = 'verification/fixes/perf030_002/static_freeze.json'
INPUTS_PATH = 'verification/fixes/perf030_001/inputs.json'
WORKER_PATH = 'verification/perf030_002_worker.py'
RESULTS_PATH = 'verification/perf030_002_results.py'
MODES = ('cold', 'pose_miss', 'geometry_miss', 'hot')
ENTRIES = ('measure_pair_geometry', 'task_result')
JSON_SAVE_LEDGER = []


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def remaining(deadline):
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise TimeoutError('PERF030_002 deadline exhausted')
    return seconds


def save(path, value):
    started = time.perf_counter_ns()
    blob = (json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode('utf8')
    with path.open('xb') as stream:
        stream.write(blob)
        stream.flush()
    JSON_SAVE_LEDGER.append({'path': str(path), 'bytes': len(blob),
                             'encode_write_flush_ns': time.perf_counter_ns() - started})


def relative_path(value):
    path = PurePosixPath(value)
    if (path.is_absolute() or path.as_posix() != value or '\\' in value
            or any(part in ('', '.', '..') or ':' in part for part in path.parts)):
        raise ValueError('invalid frozen relative path ' + repr(value))
    return path


def git(arguments, deadline):
    completed = subprocess.run(['git', *arguments], cwd=ROOT, capture_output=True,
                               timeout=remaining(deadline), check=True)
    return completed.stdout


def export_files(commit, paths, destination, deadline, expected=None):
    """Read selected Git archive members, then publish only those exact bytes."""
    names = set(paths)
    for name in names:
        relative_path(name)
    raw = git(['archive', '--format=tar', commit, '--', *sorted(names)], deadline)
    sources = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        for member in archive.getmembers():
            remaining(deadline)
            if member.isdir():
                continue
            if member.name not in names or not member.isfile():
                raise ValueError('unexpected archive member ' + member.name)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError('unreadable archive member ' + member.name)
            blob = stream.read()
            if member.name in sources:
                raise ValueError('duplicate archive member ' + member.name)
            if expected is not None:
                row = expected[member.name]
                if sha(blob) != row['sha256'] or len(blob) != row['bytes']:
                    raise ValueError('frozen QA bytes differ ' + member.name)
            sources[member.name] = blob
    if set(sources) != names:
        raise ValueError('archive missing frozen files ' + repr(sorted(names - set(sources))))
    for name, blob in sources.items():
        remaining(deadline)
        target = destination.joinpath(*relative_path(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(blob)
    return sources


def runtime_snapshot(commit, destination, deadline):
    paths = git(['ls-tree', '-r', '--name-only', commit, '--',
                 'human_eye_plugin', 'human_eye_module1_operators', *ROOT_MODULES], deadline)
    selected = []
    for name in paths.decode('utf8').splitlines():
        parts = PurePosixPath(name).parts
        package_source = (len(parts) == 2 and parts[0] in
                          ('human_eye_plugin', 'human_eye_module1_operators')
                          and name.endswith('.py'))
        if name in ROOT_MODULES or package_source:
            selected.append(name)
    if len(selected) != 130 or not set(ROOT_MODULES).issubset(selected):
        raise ValueError('runtime source inventory differs from the frozen 130 files')
    sources = export_files(commit, selected, destination, deadline)
    identity_tree = ast.parse(sources['human_eye_plugin/runtime_identity.py'])
    literals = {}
    for node in identity_tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in {
                        'BASE_VERSION', 'IMPLEMENTATION_REVISION', '_ROOT_MODULES'}:
                    literals[target.id] = ast.literal_eval(node.value)
    if tuple(literals['_ROOT_MODULES']) != ROOT_MODULES:
        raise ValueError('runtime root module policy differs')
    files = [{'path': name, 'sha256': sha(blob)} for name, blob in sorted(sources.items())]
    digest_input = {'base_version': literals['BASE_VERSION'],
                    'implementation_revision': literals['IMPLEMENTATION_REVISION'], 'files': files}
    source_digest = sha(json.dumps(digest_input, sort_keys=True, separators=(',', ':'),
                                  ensure_ascii=True).encode('utf8'))
    manifest = {'commit': commit, 'source_sha256': source_digest, **digest_input}
    return manifest


def frozen_qa(run_freeze, destination, deadline):
    rows = {row['path']: row for row in run_freeze['files']}
    if len(rows) != len(run_freeze['files']):
        raise ValueError('duplicate QA manifest path')
    normal = [name for name in rows if name != GEOMETRY_PATH]
    sources = export_files(run_freeze['qa_commit'], normal, destination, deadline, rows)
    if GEOMETRY_PATH in rows:
        sources.update(export_files(CANDIDATE, [GEOMETRY_PATH], destination, deadline, rows))
    for required in (STATIC_FREEZE, INPUTS_PATH, WORKER_PATH, RESULTS_PATH):
        if required not in sources:
            raise ValueError('QA manifest missing ' + required)
    if sha(sources[STATIC_FREEZE]) != run_freeze['static_freeze_sha256']:
        raise ValueError('original static freeze differs')
    original = json.loads(sources[STATIC_FREEZE])
    for row in original['files']:
        if row['path'] not in sources or sha(sources[row['path']]) != row['sha256']:
            raise ValueError('original static file differs ' + row['path'])
    controller = 'verification/perf030_002_run.py'
    if controller not in sources or sha(Path(__file__).read_bytes()) != sha(sources[controller]):
        raise ValueError('running controller differs from frozen QA controller')
    manifest = {'commit': run_freeze['qa_commit'],
                'files': [{'path': name, 'sha256': sha(blob)}
                          for name, blob in sorted(sources.items())]}
    return sources, manifest


class Worker:
    def __init__(self, arm, root, qa_root, runtime_manifest, qa_manifest,
                 worker_sha, output, deadline):
        self.arm = arm
        self.output = output
        self.events = queue.Queue()
        self.stdout_publish_ns = 0
        self.roundtrip_ns = defaultdict(int)
        self.stderr = (output / (arm + '_stderr.log')).open('xb')
        self.stdout = (output / (arm + '_stdout.jsonl')).open('x', encoding='utf8')
        bootstrap = '\n'.join([
            'import hashlib,sys,types', 'from pathlib import Path',
            'path=Path(sys.argv[1]);expected=sys.argv[2];blob=path.read_bytes()',
            "if hashlib.sha256(blob).hexdigest()!=expected: raise ValueError('QA worker bytes differ')",
            "sys.argv=[str(path),*sys.argv[3:]]",
            "module=types.ModuleType('__main__');module.__file__=str(path);module.__package__=None",
            "sys.modules['__main__']=module",
            "exec(compile(blob,str(path),'exec',dont_inherit=True),module.__dict__)",
        ])
        environment = dict(os.environ)
        for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
            environment[name] = '1'
        environment['PYTHONIOENCODING'] = 'utf-8'
        command = [sys.executable, '-I', '-u', '-c', bootstrap,
                   str(qa_root / WORKER_PATH), worker_sha, '--root', str(root),
                   '--qa-root', str(qa_root), '--runtime-manifest', str(runtime_manifest),
                   '--qa-manifest', str(qa_manifest), '--inputs', str(qa_root / INPUTS_PATH),
                   '--arm', arm]
        started = time.perf_counter_ns()
        try:
            self.process = subprocess.Popen(command, cwd=root, env=environment,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                text=True, encoding='utf8', bufsize=1,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except BaseException:
            self.stderr.close()
            self.stdout.close()
            raise
        self.reader = threading.Thread(target=self._read_stdout, daemon=True)
        try:
            self.reader.start()
        except BaseException:
            self.process.kill()
            self.process.wait(timeout=max(.05, deadline + 5 - time.monotonic()))
            self.stderr.close()
            self.stdout.close()
            raise
        self.started_ns = started
        self.start_ready_ns = 0

    def wait_ready(self, deadline):
        self.ready = self.receive(deadline)
        self.start_ready_ns = time.perf_counter_ns() - self.started_ns
        if self.ready.get('event') != 'ready' or self.ready.get('arm') != self.arm:
            raise ValueError('worker did not become ready ' + repr(self.ready))

    def _read_stdout(self):
        try:
            for line in self.process.stdout:
                started = time.perf_counter_ns()
                self.stdout.write(line)
                self.stdout.flush()
                self.stdout_publish_ns += time.perf_counter_ns() - started
                self.events.put(line)
        except BaseException as exc:
            self.events.put(exc)
        finally:
            self.events.put(None)

    def receive(self, deadline):
        try:
            value = self.events.get(timeout=remaining(deadline))
        except queue.Empty as exc:
            raise TimeoutError('worker response deadline ' + self.arm) from exc
        if value is None:
            raise RuntimeError('worker exited before response ' + self.arm)
        if isinstance(value, BaseException):
            raise value
        event = json.loads(value)
        if event.get('event') == 'error':
            raise RuntimeError('worker error ' + self.arm + ' ' + json.dumps(event))
        return event

    def request(self, op, request_id, deadline, **fields):
        started = time.perf_counter_ns()
        self.process.stdin.write(json.dumps({'op': op, 'request_id': request_id, **fields}) + '\n')
        self.process.stdin.flush()
        response = self.receive(deadline)
        elapsed = time.perf_counter_ns() - started
        self.roundtrip_ns[op] += elapsed
        if op == 'finish':
            if response.get('event') != 'finished':
                raise ValueError('invalid finish response ' + repr(response))
        elif (response.get('event') != 'result' or response.get('op') != op
              or response.get('request_id') != request_id):
            raise ValueError('worker response order differs ' + repr(response))
        return response['result'], elapsed

    def close(self, deadline):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=max(.05, deadline - time.monotonic()))
        self.reader.join(timeout=max(0, deadline - time.monotonic()))
        self.process.stdin.close()
        self.process.stdout.close()
        self.stdout.close()
        self.stderr.close()


def ensure_window(token):
    state = json.loads(STATE.read_bytes())
    window = state['performance_window']
    expected = {'owner': 'M3', 'cycle_id': 'PERF-030-002', 'token': token, 'status': 'granted'}
    if any(window.get(name) != value for name, value in expected.items()):
        raise ValueError('PERF030_002 window grant does not match STATE')
    return state


def main():
    started = time.monotonic()
    JSON_SAVE_LEDGER.clear()
    absolute_deadline = started + 300
    work_deadline = absolute_deadline - 5
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--window-token', required=True)
    args = parser.parse_args()
    state = ensure_window(args.window_token)
    freeze_bytes = args.freeze.read_bytes()
    registration = json.loads(freeze_bytes)
    if registration['baseline_commit'] != BASELINE or registration['candidate_commit'] != CANDIDATE:
        raise ValueError('unexpected fixed product commits')
    if registration['baseline_runtime_source_sha256'] != BASELINE_SOURCE:
        raise ValueError('unexpected baseline source digest')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT.resolve()):
        raise ValueError('output must stay in the M3 worktree')
    output.mkdir(parents=True, exist_ok=False)
    workers = []
    clients = {}
    rows = []
    input_records = {}
    inputs = None
    stats = None
    errors = []
    correctness = None
    completed = False
    costs = {'snapshot_export_ns': {}, 'worker_start_ready_ns': {},
             'worker_formal_costs': {'baseline': defaultdict(int), 'candidate': defaultdict(int)},
             'record_publish_ns': 0, 'formal_records': 0}

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
        save(output / 'registration.json', {'run_freeze_sha256': sha(freeze_bytes),
            'run_freeze': registration, 'window_token': args.window_token,
            'window_snapshot': state, 'main_started_monotonic': started,
            'wall_budget_seconds': 300, 'cleanup_reserved_seconds': 5,
            'python': sys.version, 'executable': sys.executable})
        qa_root = output / 'qa'
        stage_started = time.perf_counter_ns()
        qa_sources, qa_manifest = frozen_qa(registration, qa_root, work_deadline)
        costs['qa_export_ns'] = time.perf_counter_ns() - stage_started
        inputs = json.loads(qa_sources[INPUTS_PATH])
        if len(inputs['cases']) != 12:
            raise ValueError('formal input count differs')
        stage_started = time.perf_counter_ns()
        stats = types.ModuleType('_perf030_002_fixed_results')
        stats.__file__ = str(qa_root / RESULTS_PATH)
        sys.modules[stats.__name__] = stats
        exec(compile(qa_sources[RESULTS_PATH], stats.__file__, 'exec', dont_inherit=True), stats.__dict__)
        costs['summary_module_init_ns'] = time.perf_counter_ns() - stage_started
        qa_manifest_path = output / 'qa_manifest.json'
        save(qa_manifest_path, qa_manifest)
        manifests = {}
        for arm, commit in (('baseline', BASELINE), ('candidate', CANDIDATE)):
            stage_started = time.perf_counter_ns()
            root = output / ('runtime_' + arm)
            manifests[arm] = runtime_snapshot(commit, root, work_deadline)
            costs['snapshot_export_ns'][arm] = time.perf_counter_ns() - stage_started
            manifest_path = output / (arm + '_runtime_manifest.json')
            save(manifest_path, manifests[arm])
        if manifests['baseline']['source_sha256'] != BASELINE_SOURCE:
            raise ValueError('exported E identity differs')
        before = {row['path']: row['sha256'] for row in manifests['baseline']['files']}
        after = {row['path']: row['sha256'] for row in manifests['candidate']['files']}
        if set(before) != set(after) or [name for name in before if before[name] != after[name]] != [GEOMETRY_PATH]:
            raise ValueError('candidate product change extends beyond PT geometry file')
        if after[GEOMETRY_PATH] != CANDIDATE_GEOMETRY:
            raise ValueError('candidate geometry differs from original static freeze')
        for arm in ('baseline', 'candidate'):
            client = Worker(arm, output / ('runtime_' + arm), qa_root,
                output / (arm + '_runtime_manifest.json'), qa_manifest_path,
                sha(qa_sources[WORKER_PATH]), output, work_deadline)
            workers.append(client)
            clients[arm] = client
            client.wait_ready(work_deadline)
            costs['worker_start_ready_ns'][arm] = client.start_ready_ns
            save(output / (arm + '_ready.json'), client.ready)
            if client.ready['identity']['runtime']['source_sha256'] != manifests[arm]['source_sha256']:
                raise ValueError('executed runtime identity differs ' + arm)
        probes = {}
        for arm in ('baseline', 'candidate'):
            probes[arm], _ = clients[arm].request('probes', arm + '-probes', work_deadline)
            save(output / (arm + '_probes.json'), probes[arm])
        tests, _ = clients['candidate'].request('tests', 'candidate-tests', work_deadline)
        save(output / 'candidate_tests.json', tests)
        correctness = (probes['baseline'].get('passed') is True
                       and probes['candidate'].get('passed') is True and tests.get('passed') is True)
        save(output / 'correctness_gate.json', {'passed': correctness,
            'baseline_probe_protocol_passed': probes['baseline'].get('passed'),
            'candidate_probe_passed': probes['candidate'].get('passed'),
            'candidate_tests_passed': tests.get('passed')})
        if correctness:
            with (output / 'formal_raw.jsonl').open('x', encoding='utf8') as raw:
                for case_index, case in enumerate(inputs['cases']):
                    for block in range(5):
                        for mode in MODES:
                            for entry in ENTRIES:
                                for repeat in range(3):
                                    arms = ('baseline', 'candidate') if block % 2 == 0 else ('candidate', 'baseline')
                                    for arm in arms:
                                        remaining(work_deadline)
                                        request_id = 'formal-' + str(len(rows))
                                        result, elapsed = clients[arm].request('sample', request_id, work_deadline,
                                            case_index=case_index, mode=mode, entry=entry)
                                        row = {'case_index': case_index, 'case': case['name'], 'group': case['group'],
                                            'block': block, 'mode': mode, 'entry': entry, 'repeat': repeat,
                                            'arm': arm, 'result': result, 'controller_roundtrip_ns': elapsed}
                                        rows.append(row)
                                        publishing = time.perf_counter_ns()
                                        raw.write(json.dumps(row, ensure_ascii=True, allow_nan=False) + '\n')
                                        raw.flush()
                                        costs['record_publish_ns'] += time.perf_counter_ns() - publishing
                                        costs['formal_records'] = len(rows)
                                        for name, value in result['costs'].items():
                                            if isinstance(value, int):
                                                costs['worker_formal_costs'][arm][name] += value
                                        if result.get('exception'):
                                            raise RuntimeError('formal sample failed ' + json.dumps(result['exception']))
                                        record = result['modified_input']
                                        key = str(case_index) + '/' + mode
                                        saved = input_records.setdefault(key, {'case_index': case_index,
                                            'case': case['name'], 'mode': mode, 'arms': {}})
                                        previous = saved['arms'].setdefault(arm, record)
                                        if previous['sha256'] != record['sha256']:
                                            raise ValueError('same arm modified input changed ' + key)
                                        if len(saved['arms']) == 2 and saved['arms']['baseline']['sha256'] != saved['arms']['candidate']['sha256']:
                                            raise ValueError('arm modified inputs differ ' + key)
            if len(rows) != 2880:
                raise ValueError('formal record count differs')
            prime_calls = sum(costs['worker_formal_costs'][arm]['prime_calls'] for arm in clients)
            if prime_calls != 2160:
                raise ValueError('formal prime call count differs ' + str(prime_calls))
        for arm in ('baseline', 'candidate'):
            result, _ = clients[arm].request('finish', arm + '-finish', work_deadline)
            save(output / (arm + '_finished.json'), result)
        completed = True
    except BaseException as exc:
        errors.append({'type': type(exc).__name__, 'message': str(exc),
                       'traceback': traceback.format_exc(), 'formal_records_preserved': len(rows)})
    finally:
        cleanup_started = time.perf_counter_ns()
        for client in workers:
            if client.process.poll() is None:
                client.process.kill()
        for client in workers:
            try:
                client.close(absolute_deadline)
            except BaseException as exc:
                errors.append({'stage': 'worker_cleanup', 'arm': client.arm,
                               'type': type(exc).__name__, 'message': str(exc)})
        costs['cleanup_ns'] = time.perf_counter_ns() - cleanup_started
        costs['worker_roundtrip_ns'] = {client.arm: dict(client.roundtrip_ns) for client in workers}
        costs['worker_stdout_publish_ns'] = {client.arm: client.stdout_publish_ns for client in workers}
        if stats is not None and inputs is not None:
            try:
                summary_started = time.perf_counter_ns()
                save(output / 'summary.json', stats.summarize(rows, inputs))
                costs['summary_and_publish_ns'] = time.perf_counter_ns() - summary_started
            except BaseException as exc:
                errors.append({'stage': 'summary', 'type': type(exc).__name__, 'message': str(exc)})
        costs['total_wall_ns_before_seal'] = int((time.monotonic() - started) * 1e9)
        save(output / 'modified_inputs.json', list(input_records.values()))
        save(output / 'errors.json', errors)
        save(output / 'costs.json', costs)
        save(output / 'run_status.json', {'completed_protocol': completed, 'correctness_passed': correctness,
            'formal_records': len(rows), 'formal_complete': len(rows) == 2880,
            'errors': len(errors), 'elapsed_seconds_before_status': time.monotonic() - started,
            'within_300_seconds_before_status': time.monotonic() <= absolute_deadline,
            'all_workers_reaped': all(client.process.poll() is not None for client in workers)})
        save(output / 'completion_timing.json', {
            'total_wall_ns_through_artifact_seal': int((time.monotonic() - started) * 1e9),
            'json_save_publications': list(JSON_SAVE_LEDGER),
            'json_save_totals': {'files': len(JSON_SAVE_LEDGER),
                'bytes': sum(item['bytes'] for item in JSON_SAVE_LEDGER),
                'encode_write_flush_ns': sum(item['encode_write_flush_ns'] for item in JSON_SAVE_LEDGER)},
            'terminal_timing_publication_excluded': True})
    watchdog.cancel()
    return 0 if completed and not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
