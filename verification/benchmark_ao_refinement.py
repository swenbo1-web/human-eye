"""Frozen AO A / independent R / optimized descriptive D comparison.

Run with --candidate PATH --blender PATH --output-dir NEW [--pilot].
Each arm encodes original facts afresh, including both publications for actions.
This benchmark produces evidence and numeric gates; root owns final acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import fields, is_dataclass
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path
import platform
import shutil
import statistics
import struct
import subprocess
import sys
from time import perf_counter_ns
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

METHODS = ('A', 'R', 'D')
PERMUTATIONS = tuple(itertools.permutations(METHODS))
GROUPS = {'BC': tuple(range(1, 9)), 'TD': tuple(range(9, 15)),
          'VG': tuple(range(15, 19)), 'action': (19, 20)}
WARMUPS = 5
FORMAL_GROUPS = 60
PILOT_GROUPS = 12
FAMILY_GROUPS = 24  # 12 per state, even in the pilot.
BOOTSTRAP_REPLICATES = 6000
BOOTSTRAP_SEED = 20261105
A_SHA = '5d8f3982d79af6e276e2da178b7707f1513508bdd14626089006e4900c1676bf'
CONTROL_SHA = 'd6c81d30f10fa70de7d371191224d322cc1acbf5a13ddbddeb7c86c51ae7c1a8'
BASELINE = 'verification/baselines/ao_implementation.py'
BENCHMARK = 'verification/benchmark_ao_refinement.py'
SOURCES = (
    'docs/AO_ACCEPTANCE_PROTOCOL.md', 'docs/AO_REFINEMENT_PROTOCOL.md',
    'human_eye_fast/__init__.py', 'human_eye_fast/engine.py', 'human_eye_fast/kernels.py',
    'human_eye_fast/resident_bridge.py', 'human_eye_fast/blender_resident_bridge.py',
    'human_eye_fast/fast_bvh_clearance.py', 'human_eye_fast/tensor_deform.py',
    'human_eye_fast/raycast_saccade_gpu.py', 'human_eye_fast/fast_affordance_out.py',
    'human_eye_fast/control.py', 'verification/ao_fixtures.py', 'verification/vg_fixtures.py',
    'verification/test_fast_affordance_out.py', BASELINE, BENCHMARK,
)
THREADS = {key: '1' for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
           'BLIS_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS', 'PYTHONDONTWRITEBYTECODE')}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path):
    return json.loads(Path(path).read_bytes())


def _write(path, record, *, compact=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, allow_nan=False,
                  indent=None if compact else 2, separators=(',', ':') if compact else None)


def _load_encoder(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _named(columns, *values):
    return dict(zip(columns, values))


def _descriptive(module):
    project, json_bytes, version = module._project, module._json_bytes, module._BASELINE

    def encode(package):
        return json_bytes(project(package, _named, version))

    return encode


def _publications(encode, package):
    if package.outcome is None:
        return (encode(package),)
    before = type(package)((package.observations[0],))
    return encode(before), encode(package)


def _encode_batch(encode, packages):
    start = perf_counter_ns()
    result = [_publications(encode, package) for package in packages]
    return perf_counter_ns() - start, result


def _schedule(count, process_index):
    """Five warmups followed by balanced groups; parity never fixes method order."""
    for sequence in range(WARMUPS + count):
        state = sequence % 2
        permutation = (sequence // 2 + process_index) % len(PERMUTATIONS)
        yield {'sequence': sequence, 'sample_index': sequence - WARMUPS,
               'phase': 'warmup' if sequence < WARMUPS else 'measured',
               'state': state, 'permutation_index': permutation,
               'order': list(PERMUTATIONS[permutation])}


def _balanced(records, count):
    measured = [r for r in records if r['phase'] == 'measured']
    return (len(measured) == count and
            Counter((r['state'], tuple(r['order'])) for r in measured)
            == Counter({(state, order): count // 12 for state in (0, 1) for order in PERMUTATIONS}))


def _digest(value):
    """Hash all raw fact content outside timing; no serialization/producer reuse."""
    import numpy as np

    digest = hashlib.sha256()

    def emit(raw):
        digest.update(struct.pack('>Q', len(raw)))
        digest.update(raw)

    def visit(item):
        if isinstance(item, np.ndarray):
            emit(b'ndarray')
            emit(item.dtype.str.encode())
            emit(str(item.shape).encode())
            emit(item.tobytes(order='C'))
        elif isinstance(item, np.generic):
            visit(item.item())
        elif is_dataclass(item):
            emit(('dataclass:' + type(item).__module__ + '.' + type(item).__qualname__).encode())
            for field in fields(item):
                emit(field.name.encode())
                visit(getattr(item, field.name))
        elif isinstance(item, dict):
            emit(b'dict')
            for key, val in item.items():
                visit(key)
                visit(val)
        elif isinstance(item, (tuple, list)):
            emit(type(item).__name__.encode())
            emit(str(len(item)).encode())
            for val in item:
                visit(val)
        elif isinstance(item, bytes):
            emit(b'bytes')
            emit(item)
        elif isinstance(item, float):
            emit(b'float64')
            emit(struct.pack('>d', item))
        elif isinstance(item, (str, int, bool)) or item is None:
            emit(type(item).__name__.encode())
            emit(json.dumps(item, ensure_ascii=False).encode())
        else:
            raise TypeError(f'Unsupported raw fact type: {type(item)!r}')

    visit(value)
    return digest.hexdigest()


def _source_hashes(manifest, run):
    return {name: {'original': _sha(entry['original']), 'archive': _sha(run / entry['archive'])}
            for name, entry in manifest['sources'].items()}


def _assert_source_hashes(manifest, hashes):
    for name, values in hashes.items():
        assert values['original'] == values['archive'] == manifest['sources'][name]['sha256'], name


def _metadata(result, cases):
    sizes, hashes, publications = [], [], []
    for case, messages in zip(cases, result, strict=True):
        phases = ('before', 'final') if case >= 19 else ('final',)
        assert len(messages) == len(phases)
        row_sizes = []
        for phase, payload in zip(phases, messages, strict=True):
            assert isinstance(payload, bytes)
            size, digest = len(payload), hashlib.sha256(payload).hexdigest()
            row_sizes.append(size)
            hashes.append(digest)
            publications.append({'case_id': f'{case:02}', 'phase': phase, 'bytes': size, 'sha256': digest})
        sizes.append(sum(row_sizes))
    return {'task_bytes': sizes, 'publication_bytes': [p['bytes'] for p in publications],
            'publication_sha256': hashes, 'publications': publications}


def _measure_series(encoders, states, cases, count, process_index, scope):
    inputs = [tuple(packages[i - 1] for i in cases) for packages in states]
    records, retained = [], []
    for plan in _schedule(count, process_index):
        record = {**plan, 'scope': scope, 'cases': list(cases), 'elapsed_ns': {}}
        outputs = {}
        for method in plan['order']:
            elapsed, result = _encode_batch(encoders[method], inputs[plan['state']])
            record['elapsed_ns'][method] = elapsed
            outputs[method] = result
        # Retain bytes; no hashing, scoring, or output comparison between calls/groups.
        records.append(record)
        retained.append(outputs)
    return records, retained


def _verify_series(records, retained, references, failures, out):
    for record, outputs in zip(records, retained, strict=True):
        record['outputs'] = {m: _metadata(outputs[m], record['cases']) for m in METHODS}
        record['A_R_exact_bytes'] = outputs['A'] == outputs['R']
        for method in METHODS:
            expected = [references[record['state']][method][i - 1] for i in record['cases']]
            ok = outputs[method] == expected
            record.setdefault('same_as_state_reference', {})[method] = ok
            if not ok or (method in ('A', 'R') and not record['A_R_exact_bytes']):
                key = f"{record['scope']}-{record['sequence']}-{method}"
                failures.append(key)
                for case, messages in zip(record['cases'], outputs[method], strict=True):
                    for index, payload in enumerate(messages):
                        path = out / 'failed-publications' / key / f'{case:02}-{index}.json'
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_bytes(payload)


def _snapshot_probe(encoders, schema, private):
    """Same package identity, raw borrowed array changes: forbid a content cache."""
    import numpy as np
    from human_eye_fast.fast_affordance_out import AffordancePackage, DeformationFact, ObjectFact, ObservationFact
    from human_eye_fast.resident_bridge import ResidentBridge
    from human_eye_fast.tensor_deform import compute_cross_frame_deformation_tensor
    from verification.test_fast_affordance_out import decode_public

    reference = np.array([[0., 0., 0.], [3., 0., 0.], [0., 3., 0.]])
    triangles = np.array([[0, 1, 2]], dtype=np.int32)
    bridge = ResidentBridge()
    object_id = 'snapshot-\u4e2d-\U0001f441'
    mesh = bridge.add(object_id, reference + [1., 0., 0.], triangles, np.eye(4))
    metrics = compute_cross_frame_deformation_tensor([mesh.world_m], triangles, reference_vertices=reference)
    fact = DeformationFact(object_id, 7, [8], metrics, triangles, 8, mesh.world_m)
    package = AffordancePackage((ObservationFact('unchanged-observation-id', 8,
        (ObjectFact(object_id, 1, (-0.0, 0.0, 1.0)),), deformation=fact),))
    before_digest = _digest(package)
    old = {m: encoders[m](package) for m in METHODS}
    old_hashes = {m: hashlib.sha256(v).hexdigest() for m, v in old.items()}
    old_values = {m: decode_public(v, schema) for m, v in old.items()}
    bridge.update_full(object_id, reference + [2., 0., 0.])
    fresh = compute_cross_frame_deformation_tensor([mesh.world_m], triangles, reference_vertices=reference)
    for key, value in fresh.items():
        metrics[key][...] = value
    new = {m: encoders[m](package) for m in METHODS}
    after_digest = _digest(package)
    new_values = {m: decode_public(v, schema) for m, v in new.items()}
    checks = {
        'same_package_identity_used': True,
        'input_digest_changed': before_digest != after_digest,
        'each_encoder_reflects_caller_update': all(old[m] != new[m] for m in METHODS),
        'returned_bytes_unchanged': all(hashlib.sha256(old[m]).hexdigest() == old_hashes[m] for m in METHODS),
        'A_R_before_after_exact': old['A'] == old['R'] and new['A'] == new['R'],
        'decoded_old_centroid_stays_old': all(v['observations'][0]['deformation']['faces'][0]['position_m'] == [2., 1., 0.] for v in old_values.values()),
        'decoded_new_centroid_is_new': all(v['observations'][0]['deformation']['faces'][0]['position_m'] == [3., 1., 0.] for v in new_values.values()),
        'negative_zero_and_unicode_preserved': all(struct.pack('>d', v['observations'][0]['objects'][0]['center_m'][0]) == struct.pack('>d', -0.0) and '\u4e2d-\U0001f441' in v['object_ids'][0] for v in (*old_values.values(), *new_values.values())),
    }
    for phase, values in (('before', old), ('after', new)):
        for method, payload in values.items():
            (private / f'caller-update-{method}-{phase}.json').write_bytes(payload)
    return {'checks': checks, 'passed': all(checks.values()), 'input_digest_before': before_digest,
            'input_digest_after': after_digest, 'before_sha256': old_hashes,
            'after_sha256': {m: hashlib.sha256(v).hexdigest() for m, v in new.items()}}


def _write_public_and_score(out, schemas, references, fixture_reports, failures, runner_executable):
    from verification.test_fast_affordance_out import decode_public

    quality, public_manifest = [], {}
    for method in METHODS:
        method_dir = out / f'method-{method}'
        method_dir.mkdir()
        schema = schemas[method]
        _write(method_dir / 'schema.json', schema, compact=True)
        suffix, arm = ('b', 'baseline') if method == 'D' else ('c', 'candidate')
        for state in range(2):
            public = method_dir / f'state-{state}'
            public.mkdir()
            fixture = fixture_reports[state]
            fixture_dir = out / 'fixtures' / f'state-{state}'
            _write(public / 'tasks.json', fixture['tasks'])
            (public / 'images').mkdir()
            for path, expected in fixture['png'].items():
                shutil.copyfile(fixture_dir / path, public / path)
                assert _sha(public / path) == expected['sha256']
            rows = []
            for case, messages in enumerate(references[state][method], 1):
                final_path = public / f'{case:02}.{suffix}.json'
                final_path.write_bytes(messages[-1])
                actual = decode_public(messages[-1], schema)
                before_matches = True
                if case >= 19:
                    before_path = public / f'{arm}-before-{case:02}.json'
                    before_path.write_bytes(messages[0])
                    before = decode_public(messages[0], schema)
                    before_matches = (before['outcome'] is None and before['object_ids'] == actual['object_ids']
                                      and before['observations'] == actual['observations'][:1])
                    if method in ('A', 'R'):
                        before_matches &= messages[0] == (fixture_dir / f'candidate-before-{case:02}.json').read_bytes()
                row = {'case_id': f'{case:02}', 'before_matches_actual_initial_publication': before_matches,
                       'publication_bytes': [len(value) for value in messages],
                       'bytes': sum(len(value) for value in messages)}
                rows.append(row)
            quality.append({'method': method, 'state': state, 'cases': rows,
                            'median_bytes': statistics.median(r['bytes'] for r in rows),
                            'total_bytes': sum(r['bytes'] for r in rows)})
        for path in method_dir.rglob('*'):
            if path.is_file():
                public_manifest[str(path.relative_to(out)).replace('\\', '/')] = {'bytes': path.stat().st_size, 'sha256': _sha(path)}
    _write(out / 'publication-evidence.json', {'conditions': quality})
    # Pillow belongs to the caller's Python environment, not Blender's bundled Python.
    # This helper runs only after every timing interval and after all public files exist.
    command = [runner_executable, '-B', str(Path(__file__).resolve()), '--score-only', '--output-dir', str(out)]
    with (out / 'scoring.log').open('xb') as log:
        completed = subprocess.run(command, cwd=ROOT, env=os.environ | THREADS,
                                   stdout=log, stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise RuntimeError(f'Parent-interpreter scoring failed: {out / "scoring.log"}')
    scoring = _load(out / 'consumption.json')
    failures.extend(scoring['failures'])
    return scoring['conditions'], public_manifest


def _score_saved(out):
    """Public image/scoring replay in the recorded parent Python, never in Blender."""
    from verification.test_fast_affordance_out import exercise_negative_controls, score_public

    conditions = _load(out / 'publication-evidence.json')['conditions']
    failures = []
    for condition in conditions:
        method, state = condition['method'], condition['state']
        method_dir = out / f'method-{method}'
        public = method_dir / f'state-{state}'
        schema = _load(method_dir / 'schema.json')
        tasks = _load(public / 'tasks.json')
        oracle = _load(out / 'private' / f'state-{state}-oracle.json')
        suffix = 'b' if method == 'D' else 'c'
        for row in condition['cases']:
            case = int(row['case_id'])
            payload = (public / f'{case:02}.{suffix}.json').read_bytes()
            row['score'] = score_public(payload, schema, public, tasks[case - 1], oracle[case - 1])
            if case in (1, 18):
                row['negative_controls'] = exercise_negative_controls(payload, schema, public, tasks[case - 1], oracle[case - 1])
            row['passed'] = (row['before_matches_actual_initial_publication'] and row['score']['passed']
                             and all(v['rejected'] for v in row.get('negative_controls', {}).values()))
            if not row['passed']:
                failures.append(f'quality-{method}-{state}-{case:02}')
        condition['passed'] = all(row['passed'] for row in condition['cases'])
    _write(out / 'consumption.json', {
        'scope': 'Author scorer in parent Python; independent root public consumer remains separate',
        'pid': os.getpid(), 'python_executable': sys.executable, 'python': sys.version,
        'conditions': conditions, 'failures': failures, 'passed': not failures})
    return 0


def _worker(args):
    import bpy
    import numpy as np
    from human_eye_fast import control
    from verification.ao_fixtures import build_state

    assert bpy.app.background
    run, out = args.run_dir, args.output_dir
    manifest = _load(run / 'source-manifest.json')
    source_before = _source_hashes(manifest, run)
    _assert_source_hashes(manifest, source_before)
    assert manifest['sources'][BASELINE]['sha256'] == A_SHA
    assert manifest['sources']['human_eye_fast/fast_affordance_out.py']['sha256'] == A_SHA
    assert manifest['sources']['human_eye_fast/control.py']['sha256'] == CONTROL_SHA
    module_a = _load_encoder(run / manifest['sources'][BASELINE]['archive'], 'human_eye_fast._ao_A')
    module_r = _load_encoder(run / manifest['sources']['candidate']['archive'], 'human_eye_fast._ao_R')
    assert module_a.Translate is module_r.Translate is control.Translate
    encoders = {'A': module_a.encode, 'R': module_r.encode, 'D': _descriptive(module_r)}
    schemas = {'A': module_a.public_schema(), 'R': module_r.public_schema(), 'D': module_r.public_schema()}
    assert schemas['A'] == schemas['R'] == schemas['D']
    private = out / 'private'
    private.mkdir()
    states, fixture_reports = [], []
    for state in range(2):
        fixture_dir = out / 'fixtures' / f'state-{state}'
        fixture_dir.mkdir(parents=True)
        packages, tasks, oracle, costs, environment = build_state(state, fixture_dir)
        assert len(packages) == len(tasks) == 20
        states.append(packages)
        _write(private / f'state-{state}-oracle.json', oracle)
        _write(fixture_dir / 'tasks.json', tasks)
        paths = {ob.image.path for package in packages for ob in package.observations if ob.image is not None}
        png = {path: {'bytes': (fixture_dir / path).stat().st_size, 'sha256': _sha(fixture_dir / path)} for path in sorted(paths)}
        fixture_reports.append({'state': state, 'tasks': tasks, 'oracle': oracle, 'costs_ns': costs,
                                'environment': environment, 'png': png,
                                'png_bytes': sum(item['bytes'] for item in png.values())})
    input_before = [[_digest(package) for package in packages] for packages in states]
    cases = tuple(range(1, 21))
    cold, cold_outputs, references = [], [], []
    for state in range(2):
        order = list(PERMUTATIONS[(args.process_index + 3 * state) % 6])
        record = {'scope': 'cold', 'phase': 'cold', 'sequence': state, 'state': state,
                  'cases': list(cases), 'order': order, 'elapsed_ns': {},
                  'first_dynamic_encoder_call': state == 0}
        outputs = {}
        for method in order:
            record['elapsed_ns'][method], outputs[method] = _encode_batch(encoders[method], states[state])
        cold.append(record)
        cold_outputs.append(outputs)
        references.append(outputs)
    count = PILOT_GROUPS if args.pilot else FORMAL_GROUPS
    main_records, main_outputs = _measure_series(encoders, states, cases, count, args.process_index, 'full')
    groups = {}
    for group_index, (name, member_cases) in enumerate(GROUPS.items()):
        groups[name] = _measure_series(encoders, states, member_cases, FAMILY_GROUPS,
                                      args.process_index + group_index, name)
    # All timings have ended. Preserve raw elapsed/order evidence before validation.
    _write(out / 'timings.unverified.json', {'cold': cold, 'main': main_records,
           'groups': {name: pair[0] for name, pair in groups.items()}})
    input_after = [[_digest(package) for package in packages] for packages in states]
    failures = []
    if input_before != input_after:
        failures.append('raw-input-mutated-during-encoding')
    if not all(a != b for a, b in zip(input_before[0], input_before[1])):
        failures.append('raw-input-states-not-distinct-every-task')
    _verify_series(cold, cold_outputs, references, failures, out)
    _verify_series(main_records, main_outputs, references, failures, out)
    for group_records, group_outputs in groups.values():
        _verify_series(group_records, group_outputs, references, failures, out)
    for case in range(20):
        if not all(references[0][m][case] != references[1][m][case] for m in METHODS):
            failures.append(f'publication-not-changing-across-state-{case + 1:02}')
    assert _balanced(main_records, count)
    assert all(_balanced(records, FAMILY_GROUPS) for records, _ in groups.values())
    quality, public_manifest = _write_public_and_score(out, schemas, references, fixture_reports, failures,
                                                     manifest['runner_executable'])
    snapshot = _snapshot_probe(encoders, schemas['A'], private)
    _write(private / 'caller-update.json', snapshot)
    if not snapshot['passed']:
        failures.append('caller-update-probe')
    source_after = _source_hashes(manifest, run)
    try:
        _assert_source_hashes(manifest, source_after)
    except AssertionError as error:
        failures.append('source-changed-' + str(error))
    worker = {
        'mode': 'pilot' if args.pilot else 'formal', 'pid': os.getpid(), 'process_index': args.process_index,
        'platform': platform.platform(), 'cpu': platform.processor(), 'logical_cpus': os.cpu_count(),
        'python': sys.version, 'numpy': np.__version__, 'blender': bpy.app.version_string,
        'blender_build_hash': bpy.app.build_hash.decode(), 'background': bpy.app.background,
        'thread_environment': {key: os.environ.get(key) for key in THREADS},
        'clock': vars(__import__('time').get_clock_info('perf_counter')),
        'module_names': {'A': module_a.__name__, 'R': module_r.__name__},
        'shared_control_translate_identity': True,
        'source_sha256_before': source_before, 'source_sha256_after': source_after,
        'input_before': input_before, 'input_after': input_after,
        'input_digest_definition': 'All dataclass fields, arrays/dtype/shape/raw bytes, metadata, PNG bytes; independent from producer; outside timers.',
        'schema_bytes_once_by_method': {m: (out / f'method-{m}/schema.json').stat().st_size for m in METHODS},
        'fixtures': [{k: v for k, v in report.items() if k not in ('tasks', 'oracle')} for report in fixture_reports],
        'cold': cold, 'warmups': [r for r in main_records if r['phase'] == 'warmup'],
        'samples': [r for r in main_records if r['phase'] == 'measured'],
        'groups': {name: {'warmups': [r for r in records if r['phase'] == 'warmup'],
                          'samples': [r for r in records if r['phase'] == 'measured']} for name, (records, _) in groups.items()},
        'cold_scope': 'First full batch of each dynamic method for each state; only state 0 is its first method call. R and D share optimized helpers/configuration, so their shared primitives may already be warm. Fixtures already called production A for real action selection; static imports/schema and actual scene generation are excluded. This is not process-startup or full-chain latency.',
        'quality': {'passed': not failures, 'failures': failures,
                    'author_scored_tasks': sum(len(q['cases']) for q in quality),
                    'independent_root_consumer': 'not run by this benchmark'},
        'caller_update': snapshot, 'public_artifacts': public_manifest,
    }
    _write(out / 'worker.json', worker)
    return int(bool(failures))


def _statistics(rows):
    import numpy as np

    values = {m: [row['elapsed_ns'][m] for row in rows] for m in METHODS}
    medians = {m: float(np.median(v)) for m, v in values.items()}
    tails = {m: float(np.quantile(v, .95, method='linear')) for m, v in values.items()}
    return {'count': len(rows), 'median_ns': medians, 'p95_ns': tails,
            'R_A_median_ratio': medians['R'] / medians['A'],
            'R_A_p95_ratio': tails['R'] / tails['A'],
            'R_D_p95_ratio': tails['R'] / tails['D'],
            'median_difference_R_minus_A_ns': medians['R'] - medians['A'],
            'median_paired_delta_R_minus_A_ns': float(np.median([r['elapsed_ns']['R'] - r['elapsed_ns']['A'] for r in rows]))}


def _bootstrap(workers):
    import numpy as np

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    strata = []
    for worker in workers:
        for state in (0, 1):
            rows = [r for r in worker['samples'] if r['state'] == state]
            strata.append(np.array([(r['elapsed_ns']['A'], r['elapsed_ns']['R']) for r in rows], dtype=np.float64))
    statistics_rows = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = np.concatenate([values[rng.integers(0, len(values), len(values))] for values in strata])
        statistics_rows.append(float(np.median(sample[:, 1]) - np.median(sample[:, 0])))
    return {'seed': BOOTSTRAP_SEED, 'replicates': BOOTSTRAP_REPLICATES,
            'stratification': 'process and state; independently resample paired A/R group rows within each stratum, original stratum sizes retained',
            'statistic': 'pooled median(R) minus pooled median(A), ns',
            'strata_sizes': [len(v) for v in strata],
            'percentile_95_ci_ns': np.quantile(statistics_rows, [.025, .975], method='linear').tolist()}


def _summarize(workers, pilot):
    expected_processes = 1 if pilot else 3
    expected_groups = PILOT_GROUPS if pilot else FORMAL_GROUPS
    assert len(workers) == len({w['pid'] for w in workers}) == expected_processes
    for index, worker in enumerate(workers):
        assert worker['background'] and worker['process_index'] == index
        assert len(worker['warmups']) == WARMUPS
        assert _balanced(worker['samples'], expected_groups)
        assert all(len(v['warmups']) == WARMUPS and _balanced(v['samples'], FAMILY_GROUPS) for v in worker['groups'].values())
    samples = [r for w in workers for r in w['samples']]
    pooled = _statistics(samples)
    process = [{'pid': w['pid'], 'process_index': w['process_index'], **_statistics(w['samples'])} for w in workers]
    state = {str(s): _statistics([r for r in samples if r['state'] == s]) for s in (0, 1)}
    groups = {name: _statistics([r for w in workers for r in w['groups'][name]['samples']]) for name in GROUPS}
    group_states = {name: {str(s): _statistics([r for w in workers for r in w['groups'][name]['samples'] if r['state'] == s]) for s in (0, 1)} for name in GROUPS}
    bootstrap = _bootstrap(workers)
    byte_rows = []
    for worker in workers:
        for state_index in range(2):
            row = next(r for r in worker['samples'] if r['state'] == state_index)
            medians = {m: statistics.median(row['outputs'][m]['task_bytes']) for m in METHODS}
            byte_rows.append({'process_index': worker['process_index'], 'state': state_index,
                              'task_bytes': {m: row['outputs'][m]['task_bytes'] for m in METHODS},
                              'publication_bytes': {m: row['outputs'][m]['publication_bytes'] for m in METHODS},
                              'total_bytes': {m: sum(row['outputs'][m]['task_bytes']) for m in METHODS},
                              'median_bytes': medians, 'R_D_median_byte_ratio': medians['R'] / medians['D']})
    numeric_gates = {
        'pooled_R_A_median_le_0_95': pooled['R_A_median_ratio'] <= .95,
        'pooled_R_A_p95_le_0_95': pooled['R_A_p95_ratio'] <= .95,
        'each_process_R_A_median_le_0_95': all(p['R_A_median_ratio'] <= .95 for p in process),
        'stratified_paired_median_difference_CI_upper_lt_zero': bootstrap['percentile_95_ci_ns'][1] < 0,
        'each_state_R_A_p95_le_1_05': all(p['R_A_p95_ratio'] <= 1.05 for p in state.values()),
        'each_group_R_A_p95_le_1_05': all(p['R_A_p95_ratio'] <= 1.05 for p in groups.values()),
        'original_R_D_p95_le_1_10': pooled['R_D_p95_ratio'] <= 1.10,
        'original_each_state_median_bytes_R_D_le_0_70': all(p['R_D_median_byte_ratio'] <= .70 for p in byte_rows),
    }
    evidence_gates = {'quality_and_byte_equivalence': all(w['quality']['passed'] for w in workers),
                      'raw_facts_unmodified': all(w['input_before'] == w['input_after'] for w in workers),
                      'caller_update_and_returned_bytes': all(w['caller_update']['passed'] for w in workers)}
    return {'mode': 'pilot' if pilot else 'formal', 'formal_acceptance_eligible': not pilot,
            'final_acceptance': 'not issued; independent root source audit and public consumer required',
            'numeric_gates': numeric_gates, 'evidence_gates': evidence_gates,
            'measured_gates_met': all(numeric_gates.values()) and all(evidence_gates.values()),
            'three_way_group_count': len(samples), 'tasks_per_full_batch': 20, 'publications_per_full_batch': 22,
            'overall': pooled, 'per_process': process, 'per_state': state,
            'groups_separate_from_main': groups, 'group_states_disclosure': group_states,
            'bootstrap': bootstrap, 'bytes_by_process_state': byte_rows,
            'schema_bytes_once_by_process': [w['schema_bytes_once_by_method'] for w in workers],
            'png_bytes_separate_by_process_state': [[f['png_bytes'] for f in w['fixtures']] for w in workers],
            'cold_separate': [{'pid': w['pid'], 'scope': w['cold_scope'], 'samples': w['cold']} for w in workers],
            'external_model_runs': 0}


def _parent(args):
    out = args.output_dir
    if out.exists():
        raise FileExistsError(f'Refusing to overwrite prior evidence: {out}')
    if not args.candidate.is_file() or not args.blender.is_file():
        raise FileNotFoundError('Both --candidate and --blender must be existing files')
    assert _sha(ROOT / BASELINE) == A_SHA, 'Frozen A source mismatch'
    assert _sha(ROOT / 'human_eye_fast/fast_affordance_out.py') == A_SHA, 'Production AO must remain frozen A for fixture creation'
    assert _sha(ROOT / 'human_eye_fast/control.py') == CONTROL_SHA, 'Control changed'
    out.mkdir(parents=True)
    sources = {}
    for name, original in [(name, ROOT / name) for name in SOURCES] + [('candidate', args.candidate)]:
        archive = Path('source') / ('candidate.py' if name == 'candidate' else name)
        target = out / archive
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        sources[name] = {'original': str(original.resolve()), 'archive': archive.as_posix(), 'sha256': _sha(target)}
    manifest = {'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'sources': sources, 'runner_python': sys.version, 'runner_executable': sys.executable,
                'runner_platform': platform.platform(),
                'blender_executable': str(args.blender), 'thread_environment': THREADS,
                'config': {'mode': 'pilot' if args.pilot else 'formal', 'processes': 1 if args.pilot else 3,
                           'warmups': WARMUPS, 'main_groups_per_process': PILOT_GROUPS if args.pilot else FORMAL_GROUPS,
                           'family_groups_per_process': FAMILY_GROUPS, 'states': 2,
                           'method_permutations': PERMUTATIONS, 'groups': GROUPS,
                           'bootstrap_seed': BOOTSTRAP_SEED, 'bootstrap_replicates': BOOTSTRAP_REPLICATES},
                'boundary': 'Each timer performs original-fact projection, nonfinite handling, UTF8 encoding and action-before package construction: 20 tasks, 22 publications. Image generation/I/O, hashing, scoring and assertions excluded.'}
    _write(out / 'source-manifest.json', manifest)
    workers = []
    for index in range(manifest['config']['processes']):
        process = out / f'process-{index}'
        process.mkdir()
        command = [str(args.blender), '--background', '--factory-startup', '--disable-autoexec',
                   '--python-exit-code', '1', '--python', str(Path(__file__).resolve()), '--', '--worker',
                   '--run-dir', str(out), '--output-dir', str(process), '--process-index', str(index)]
        if args.pilot:
            command.append('--pilot')
        print(f'AO refinement {manifest["config"]["mode"]} process {index}: {process}', flush=True)
        with (process / 'blender.log').open('xb') as log:
            result = subprocess.run(command, cwd=ROOT, env=os.environ | THREADS,
                                    stdout=log, stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            _write(out / f'failure-process-{index}.json', {'process_index': index,
                'returncode': result.returncode, 'log': str(process / 'blender.log'),
                'worker_evidence_retained': (process / 'worker.json').exists(), 'summary_not_issued': True})
            raise RuntimeError(f'Worker {index} failed; retained first failure evidence in {process}')
        workers.append(_load(process / 'worker.json'))
    end_hashes = _source_hashes(manifest, out)
    _write(out / 'source-after.json', end_hashes)
    _assert_source_hashes(manifest, end_hashes)
    summary = _summarize(workers, args.pilot)
    _write(out / 'summary.json', summary)
    print(json.dumps({key: summary[key] for key in ('mode', 'overall', 'numeric_gates', 'evidence_gates', 'measured_gates_met')}, indent=2), flush=True)
    return 0 if args.pilot else int(not summary['measured_gates_met'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=lambda p: Path(p).resolve())
    parser.add_argument('--blender', type=lambda p: Path(p).resolve())
    parser.add_argument('--output-dir', required=True, type=lambda p: Path(p).resolve())
    parser.add_argument('--pilot', action='store_true', help='One process, twelve main groups; never formal acceptance.')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--score-only', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--run-dir', type=lambda p: Path(p).resolve(), help=argparse.SUPPRESS)
    parser.add_argument('--process-index', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else None)
    if not args.worker and not args.score_only and (args.candidate is None or args.blender is None):
        parser.error('--candidate and --blender are required')
    can_record_failure = args.worker or args.score_only or not args.output_dir.exists()
    try:
        if args.score_only:
            return _score_saved(args.output_dir)
        return _worker(args) if args.worker else _parent(args)
    except Exception:
        if can_record_failure and args.output_dir.exists():
            failure = args.output_dir / ('scoring-exception.json' if args.score_only else 'exception.json')
            if not failure.exists():
                _write(failure, {'pid': os.getpid(), 'worker': args.worker, 'traceback': traceback.format_exc()})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
