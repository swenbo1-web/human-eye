"""Fixed offline projection and UTF-8 encoding measurements in twelve workers."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import tracemalloc
import types


BATCH = Path(__file__).resolve().parents[1]
CYCLE = 'M4-BATCH-OBSERVATION-COVERAGE-001'
SAMPLES = 21
LANES = ('draft', 'final', 'native')
IMPLEMENTATIONS = {
    'draft': ('prototype/draft.py', 'e101bb32c9a9582f596f2e41d3d3ce02864b0f8865513b666396bb2fec1e220f'),
    'final': ('prototype/final.py', '4faa9a915fc4e139978496cf53505be248e98dc058493c2649d5e2a864a9ac73'),
    'native': ('validation/native_projection.py', '6d2d9e88d50df076ed7f2fdec43051bea4f4c5c85edd5bf0775c2cb4dd8ee3f4'),
}
MEMORY_SOURCE = BATCH.parent / 'measure_nonplanar_cancellation.py'
MEMORY_SOURCE_SHA = '85ea9434505ed72a407375b05a9ecd9a936c09ecf6143045cb6057169fd0cd02'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                       allow_nan=False) + '\n').encode('utf8')


def save(path, value):
    with path.open('xb') as stream:
        stream.write(encode(value))


def checked_bytes(path, digest):
    raw = Path(path).read_bytes()
    assert sha(raw) == digest, 'frozen_file_changed: ' + str(path)
    return raw


def memory_function():
    """Compile only the previously used memory function from its fixed source."""
    raw = checked_bytes(MEMORY_SOURCE, MEMORY_SOURCE_SHA)
    tree = ast.parse(raw)
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'process_memory')
    namespace = {'sys': sys}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(MEMORY_SOURCE), 'exec'), namespace)
    return namespace['process_memory'], sha(ast.dump(function).encode('utf8'))


def projection_module(path, digest):
    raw = checked_bytes(path, digest)
    tree = ast.parse(raw)
    allowed = {'argparse', 'copy', 'json', 'pathlib'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name in allowed for alias in node.names), 'unexpected projection import'
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module in allowed, 'unexpected projection import'
    module = types.ModuleType('_frozen_offline_projection')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def project(module, bundle, request):
    first = module.directory(bundle)
    second = module.selected_observation(bundle, request)
    return encode(first), encode(second)


def worker(order_path):
    order = json.loads(order_path.read_bytes())
    assert order['cycle_id'] == CYCLE and order['samples'] == SAMPLES
    checked_bytes(Path(__file__), order['runner_sha256'])
    process_memory, memory_ast_sha = memory_function()
    module = projection_module(Path(order['implementation']), order['implementation_sha256'])
    bundle = json.loads(checked_bytes(order['bundle'], order['bundle_sha256']))
    request = json.loads(checked_bytes(order['request'], order['request_sha256']))
    inputs_before = (encode(bundle), encode(request))
    reference = project(module, bundle, request)
    samples = []
    for number in range(SAMPLES):
        began = time.perf_counter_ns()
        responses = project(module, bundle, request)
        ended = time.perf_counter_ns()
        assert responses == reference, 'projection output changed between samples'
        samples.append({'sample': number + 1, 'elapsed_ns': ended - began,
                        'directory_bytes': len(responses[0]),
                        'selected_bytes': len(responses[1]),
                        'total_response_bytes': sum(map(len, responses))})
    tracemalloc.start()
    traced_before, _ = tracemalloc.get_traced_memory()
    tracemalloc.reset_peak()
    traced_responses = project(module, bundle, request)
    traced_current, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert traced_responses == reference
    assert (encode(bundle), encode(request)) == inputs_before, 'projection mutated frozen inputs'
    os_memory = process_memory()
    output = Path(order['output'])
    for name, raw in zip(('DIRECTORY.json', 'SELECTED.json'), reference):
        with (output / name).open('xb') as stream:
            stream.write(raw)
    result = {
        'cycle_id': CYCLE, 'fixture': order['fixture'], 'lane': order['lane'],
        'runtime_pid': os.getpid(), 'python': sys.executable, 'python_version': sys.version,
        'platform': sys.platform, 'order': order, 'warmup_calls': 1,
        'samples': samples, 'sample_count': SAMPLES,
        'response_sha256': {'DIRECTORY.json': sha(reference[0]), 'SELECTED.json': sha(reference[1])},
        'response_bytes': {'DIRECTORY.json': len(reference[0]), 'SELECTED.json': len(reference[1])},
        'tracemalloc': {
            'projection_calls': 1, 'before_current_bytes': traced_before,
            'after_current_bytes': traced_current, 'peak_bytes': traced_peak,
            'incremental_peak_bytes': traced_peak - traced_before,
            'scope': 'one additional two-phase projection plus UTF-8 encoding after the timed samples'},
        'OS_memory': os_memory,
        'OS_memory_scope': 'fresh worker lifetime through this snapshot, including interpreter/import/input loading, warmup, 21 samples and tracemalloc; excludes later response/result file publication',
        'memory_helper_source_sha256': MEMORY_SOURCE_SHA,
        'memory_helper_function_AST_sha256': memory_ast_sha,
        'timing_scope': 'two phase projections and two compact UTF-8 JSON encodings with final LF; input parsing, world preparation and existing relation computation excluded',
        'input_loading': 'completed before warmup; selected request already frozen',
        'input_values_unchanged': True, 'actual_host_requests': 0,
        'product_helper_calls': 0, 'model_consumers': 0, 'new_images': 0,
        'actual_cache_hit_measurement': 'unmeasured',
    }
    save(output / 'RESULT.json', result)
    print(json.dumps({'completed': True, 'fixture': order['fixture'], 'lane': order['lane']}))


def fixture_inputs(manifest):
    base = manifest['base']
    fixtures = [{'name': 'base', 'bundle': base['bundle'], 'request': base['request']}]
    expected = ('renamed_ids_reordered', 'proper_rotation_z90', 'additional_same_shape_object')
    assert tuple(row['name'] for row in manifest['variants']) == expected
    for row in manifest['variants']:
        files = {Path(item['path']).name: item for item in row['files']}
        fixtures.append({'name': row['name'], 'bundle': files['BUNDLE.json'],
                         'request': files['REQUEST_PRIMARY.json']})
    return fixtures


def controller(manifest_path, output):
    import subprocess

    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    assert manifest['cycle_id'] == CYCLE
    fixtures = fixture_inputs(manifest)
    pins = {str(manifest_path): sha(manifest_raw), str(Path(__file__).resolve()): sha(Path(__file__).read_bytes()),
            str(MEMORY_SOURCE): MEMORY_SOURCE_SHA}
    for relative, digest in IMPLEMENTATIONS.values():
        path = BATCH / relative
        checked_bytes(path, digest)
        pins[str(path)] = digest
    for fixture in fixtures:
        for key in ('bundle', 'request'):
            item = fixture[key]
            path = (BATCH / item['path']).resolve()
            raw = checked_bytes(path, item['sha256'])
            assert len(raw) == item['bytes']
            fixture[key] = {'path': str(path), 'sha256': item['sha256']}
            pins[str(path)] = item['sha256']
    checked_bytes(MEMORY_SOURCE, MEMORY_SOURCE_SHA)
    output = output.resolve()
    assert output.is_relative_to(BATCH / 'benchmark')
    output.mkdir(exist_ok=False)
    rows = []
    for fixture_number, fixture in enumerate(fixtures):
        rotation = fixture_number % len(LANES)
        lanes = LANES[rotation:] + LANES[:rotation]
        for lane in lanes:
            folder = output / fixture['name'] / lane
            folder.mkdir(parents=True, exist_ok=False)
            relative, digest = IMPLEMENTATIONS[lane]
            order = {
                'cycle_id': CYCLE, 'fixture': fixture['name'], 'lane': lane, 'samples': SAMPLES,
                'implementation': str(BATCH / relative), 'implementation_sha256': digest,
                'bundle': fixture['bundle']['path'], 'bundle_sha256': fixture['bundle']['sha256'],
                'request': fixture['request']['path'], 'request_sha256': fixture['request']['sha256'],
                'runner_sha256': pins[str(Path(__file__).resolve())],
                'manifest_sha256': sha(manifest_raw), 'output': str(folder),
            }
            order_path = folder / 'WORK_ORDER.json'
            save(order_path, order)
            argv = [sys.executable, '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()),
                    '--worker', str(order_path)]
            with (folder / 'stdout.txt').open('xb') as stdout, (folder / 'stderr.txt').open('xb') as stderr:
                process = subprocess.Popen(argv, stdout=stdout, stderr=stderr)
                exit_code = process.wait()
            receipt = {'fixture': fixture['name'], 'lane': lane, 'argv': argv,
                       'launcher_pid': process.pid, 'exit_code': exit_code}
            save(folder / 'PROCESS.json', receipt)
            rows.append(receipt)
            assert exit_code == 0, 'offline_worker_failed; preserve directory and do not replace worker'
            worker_result = json.loads((folder / 'RESULT.json').read_bytes())
            assert worker_result['order'] == order
            assert worker_result['sample_count'] == len(worker_result['samples']) == SAMPLES
            assert worker_result['warmup_calls'] == 1
            for name, digest in worker_result['response_sha256'].items():
                checked_bytes(folder / name, digest)
    comparisons = []
    for fixture in fixtures:
        folder = output / fixture['name']
        same_bytes = {}
        for name in ('DIRECTORY.json', 'SELECTED.json'):
            final_raw = (folder / 'final' / name).read_bytes()
            native_raw = (folder / 'native' / name).read_bytes()
            assert json.loads(final_raw) == json.loads(native_raw), 'final/native semantic mismatch'
            same_bytes[name] = final_raw == native_raw
            draft = json.loads((folder / 'draft' / name).read_bytes())
            if name == 'DIRECTORY.json':
                for item in draft['objects']:
                    item.pop('center', None)
            assert draft == json.loads(final_raw), 'draft/final changed facts beyond directory center'
        comparisons.append({'fixture': fixture['name'], 'final_native_semantic_equal': True,
                            'final_native_same_bytes': same_bytes,
                            'draft_final_equal_after_removing_directory_center': True})
    assert len(rows) == 12
    for path, digest in pins.items():
        checked_bytes(path, digest)
    save(output / 'RESULTS.json', {
        'cycle_id': CYCLE, 'fixed_workers': 12, 'samples_per_worker': SAMPLES,
        'fixture_order': [item['name'] for item in fixtures],
        'execution_order': rows, 'frozen_files_sha256': pins, 'comparisons': comparisons,
        'controller_python': sys.executable, 'controller_python_sha256': sha(Path(sys.executable).read_bytes()),
        'scope': 'offline retained-data projection and encoding; precomputed relations are common inputs',
        'model_consumers': 0, 'actual_host_requests': 0, 'new_images': 0,
    })
    print(json.dumps({'completed_workers': len(rows), 'output': str(output)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker', type=Path)
    args = parser.parse_args()
    if args.worker is not None:
        worker(args.worker)
    else:
        if args.manifest is None or args.output is None:
            parser.error('--manifest and --output are required')
        controller(args.manifest.resolve(), args.output)


if __name__ == '__main__':
    main()
