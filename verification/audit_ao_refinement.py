"""Independent saved-evidence audit of AO refinement; no benchmark/runtime imports.

Recomputes linear p95 and paired stratified bootstrap independently, verifies
raw timing records, sources and every publication against actual public files.
Does not run encoders, Blender, GPU, or performance sampling.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import difflib
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics
import struct

import numpy as np
from PIL import Image

METHODS = ('A', 'R', 'D')
ORDERS = tuple(itertools.permutations(METHODS))
GROUPS = {'BC': list(range(1, 9)), 'TD': list(range(9, 15)),
          'VG': list(range(15, 19)), 'action': [19, 20]}
EXPECTED = {
    'verification/baselines/ao_implementation.py': '5d8f3982d79af6e276e2da178b7707f1513508bdd14626089006e4900c1676bf',
    'human_eye_fast/fast_affordance_out.py': '5d8f3982d79af6e276e2da178b7707f1513508bdd14626089006e4900c1676bf',
    'human_eye_fast/control.py': 'd6c81d30f10fa70de7d371191224d322cc1acbf5a13ddbddeb7c86c51ae7c1a8',
    'candidate': '84d6d02c66e39367ed30993656bed07106eb9a1a80293ac670708a41183e5f6b',
    'verification/benchmark_ao_refinement.py': 'cd78362a540118b6f2ff92d4b8f4e0688734afb82a2cf7661beec299368b071c',
    'docs/AO_REFINEMENT_PROTOCOL.md': '45d36c1e04682225edab3a7a06d8bb506f51bccc9c30765660c9845134408f3f',
}
CHILDREN = {
    'package': {'observations': ('observation', True), 'outcome': ('outcome', False)},
    'observation': {'objects': ('object', True), 'clearance': ('clearance', False), 'deformation': ('deformation', False), 'image': ('image', False)},
    'clearance': {'witness_a': ('witness', False), 'witness_b': ('witness', False)},
    'deformation': {'faces': ('face', True)},
    'image': {'section': ('section', False), 'global_view': ('view', False), 'local_view': ('view', False)},
    'outcome': {'goal': ('goal', False), 'command': ('command', False)},
}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(path):
    return {str(p.relative_to(path)).replace('\\', '/'): sha(p) for p in sorted(path.rglob('*')) if p.is_file()}


def exact(left, right):
    if type(left) != type(right):
        return False
    if isinstance(left, float):
        return struct.pack('>d', left) == struct.pack('>d', right)
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(exact(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact(a, b) for a, b in zip(left, right))
    return left == right


class Checks:
    def __init__(self):
        self.count, self.errors = 0, []

    def check(self, condition, label):
        self.count += 1
        if not condition:
            self.errors.append(label)

    def eq(self, left, right, label):
        self.check(exact(left, right), label)

    def numeric(self, actual, expected, label):
        if isinstance(actual, dict):
            for key, value in actual.items():
                self.numeric(value, expected[key], label + '/' + key)
        elif isinstance(actual, list):
            self.check(len(actual) == len(expected), label + '/length')
            for i, (left, right) in enumerate(zip(actual, expected)):
                self.numeric(left, right, label + '/' + str(i))
        elif isinstance(actual, (int, float)):
            self.check(math.isclose(actual, expected, rel_tol=2e-14, abs_tol=1e-6), label)
        else:
            self.eq(actual, expected, label)


def decode(value, schema, kind='package'):
    if value is None:
        return None
    columns = schema['columns'][kind]
    if isinstance(value, list) and len(value) == len(columns):
        result = dict(zip(columns, value))
    elif isinstance(value, dict) and set(value) == set(columns):
        result = dict(value)
    else:
        raise ValueError(f'Invalid {kind} shape')
    for field, (child, many) in CHILDREN.get(kind, {}).items():
        result[field] = [decode(v, schema, child) for v in result[field]] if many else decode(result[field], schema, child)
    return result


def percentile(values, fraction):
    """Linear interpolation computed directly from ordered values."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower))


def recompute(rows):
    columns = {m: [r['elapsed_ns'][m] for r in rows] for m in METHODS}
    med = {m: float(statistics.median(v)) for m, v in columns.items()}
    tail = {m: percentile(v, .95) for m, v in columns.items()}
    return {'count': len(rows), 'median_ns': med, 'p95_ns': tail,
            'R_A_median_ratio': med['R'] / med['A'], 'R_A_p95_ratio': tail['R'] / tail['A'],
            'R_D_p95_ratio': tail['R'] / tail['D'],
            'median_difference_R_minus_A_ns': med['R'] - med['A'],
            'median_paired_delta_R_minus_A_ns': float(statistics.median(r['elapsed_ns']['R'] - r['elapsed_ns']['A'] for r in rows))}


def resample(workers):
    strata = []
    for worker in workers:
        for state in (0, 1):
            subset = [r for r in worker['samples'] if r['state'] == state]
            strata.append([(r['elapsed_ns']['A'], r['elapsed_ns']['R']) for r in subset])
    rng = np.random.default_rng(20261105)
    differences = []
    for _ in range(6000):
        a, r = [], []
        for pairs in strata:
            indices = rng.integers(0, len(pairs), size=len(pairs))
            for index in indices:
                left, right = pairs[index]
                a.append(left)
                r.append(right)
        differences.append(float(statistics.median(r) - statistics.median(a)))
    return {'seed': 20261105, 'replicates': 6000, 'strata_sizes': [len(s) for s in strata],
            'statistic': 'pooled median(R) minus pooled median(A), ns',
            'resampling': 'Independent resampling within each process/state; keep each A/R pair intact and retain original stratum sizes.',
            'percentile_95_ci_ns': [percentile(differences, .025), percentile(differences, .975)]}


def publications(public, method, cases):
    arm, suffix = ('baseline', 'b') if method == 'D' else ('candidate', 'c')
    result, case_sizes = [], []
    for case in cases:
        total = 0
        for phase in (('before', 'final') if case >= 19 else ('final',)):
            filename = f'{arm}-before-{case:02}.json' if phase == 'before' else f'{case:02}.{suffix}.json'
            path = public / filename
            size = path.stat().st_size
            total += size
            result.append({'case_id': f'{case:02}', 'phase': phase, 'bytes': size, 'sha256': sha(path)})
        case_sizes.append(total)
    return {'task_bytes': case_sizes, 'publication_bytes': [p['bytes'] for p in result],
            'publication_sha256': [p['sha256'] for p in result], 'publications': result}


def validate_series(c, records, raw, cases, expected_count, process_offset, label, outputs):
    c.eq(len(records), expected_count + 5, label + '/5 warmups + samples')
    c.eq(len(raw), len(records), label + '/raw count')
    coverage = Counter()
    for sequence, (record, source) in enumerate(zip(records, raw)):
        tag = label + '/' + str(sequence)
        c.eq({k: v for k, v in record.items() if k not in ('outputs', 'A_R_exact_bytes', 'same_as_state_reference')}, source, tag + '/unverified raw consistency')
        c.eq(record['sequence'], sequence, tag + '/sequence')
        c.eq(record['state'], sequence % 2, tag + '/state')
        c.eq(record['sample_index'], sequence - 5, tag + '/sample index')
        c.eq(record['phase'], 'warmup' if sequence < 5 else 'measured', tag + '/phase')
        c.eq(record['cases'], cases, tag + '/cases')
        permutation = (sequence // 2 + process_offset) % 6
        c.eq(record['permutation_index'], permutation, tag + '/permutation index')
        c.eq(record['order'], list(ORDERS[permutation]), tag + '/order')
        if sequence >= 5:
            coverage[(record['state'], tuple(record['order']))] += 1
        for method in METHODS:
            elapsed = record['elapsed_ns'][method]
            c.check(type(elapsed) is int and elapsed > 0, tag + '/' + method + '/positive duration')
            c.eq(record['outputs'][method], outputs[(record['state'], method, tuple(cases))], tag + '/' + method + '/all saved publications bytes and hashes')
        c.check(record['A_R_exact_bytes'] and all(record['same_as_state_reference'].values()), tag + '/runtime equality assertions')
    c.eq(dict(coverage), {(state, order): expected_count // 12 for state in (0, 1) for order in ORDERS}, label + '/state-order balance')
    return [{'state': state, 'order': list(order), 'count': count} for (state, order), count in sorted(coverage.items())]


def tail_disclosure(worker):
    rows = worker['samples']
    med = {m: statistics.median(r['elapsed_ns'][m] for r in rows) for m in METHODS}
    def row_summary(row):
        return {**{k: row[k] for k in ('sequence', 'sample_index', 'state', 'order', 'elapsed_ns')},
                'duration_over_own_process_median': {m: row['elapsed_ns'][m] / med[m] for m in METHODS},
                'R_minus_A_ns': row['elapsed_ns']['R'] - row['elapsed_ns']['A']}
    elevated = [r for r in rows if r['elapsed_ns']['R'] > 1.5 * med['R']]
    return {'pid': worker['pid'], 'process_index': worker['process_index'],
            'R_slower_than_A_pair_count': sum(r['elapsed_ns']['R'] > r['elapsed_ns']['A'] for r in rows),
            'R_highest_10_paired_rows': [row_summary(r) for r in sorted(rows, key=lambda r: r['elapsed_ns']['R'], reverse=True)[:10]],
            'descriptive_elevated_threshold': 'R > 1.5 times its own process median; descriptive only, no rows excluded',
            'elevated_R_sequence': [r['sequence'] for r in elevated],
            'elevated_R_count': len(elevated),
            'elevated_R_and_A_count': sum(r['elapsed_ns']['A'] > 1.5 * med['A'] for r in elevated),
            'elevated_R_and_D_count': sum(r['elapsed_ns']['D'] > 1.5 * med['D'] for r in elevated),
            'per_state_order': [{'state': state, 'order': list(order), **recompute([r for r in rows if r['state'] == state and tuple(r['order']) == order])} for state in (0, 1) for order in ORDERS],
            'interpretation_limit': 'Sequential durations reveal co-occurring/clustered slow groups, not their cause. CPU scheduling, GPU activity and GC events were not logged. No noise attribution or sample exclusions; the fixed supplementary run and its added diagnostic gate are assessed separately.'}


def audit_run(run, c):
    start_inventory = inventory(run)
    manifest, claimed = read(run / 'source-manifest.json'), read(run / 'summary.json')
    source_after = read(run / 'source-after.json')
    workers = [read(run / f'process-{i}/worker.json') for i in range(3)]
    c.eq(manifest['config']['mode'], 'formal', run.name + '/formal mode')
    c.eq(manifest['config']['processes'], 3, run.name + '/3 processes')
    c.eq(manifest['config']['warmups'], 5, run.name + '/5 warmups')
    c.eq(manifest['config']['main_groups_per_process'], 60, run.name + '/60 main groups')
    c.eq(manifest['config']['family_groups_per_process'], 24, run.name + '/24 family groups')
    c.eq(manifest['config']['method_permutations'], [list(v) for v in ORDERS], run.name + '/6 permutations')
    source_report = {}
    for name, entry in manifest['sources'].items():
        archived, current = sha(run / entry['archive']), sha(entry['original'])
        c.eq(archived, entry['sha256'], run.name + '/archived source/' + name)
        c.eq(current, archived, run.name + '/current source/' + name)
        c.eq(source_after[name], {'original': archived, 'archive': archived}, run.name + '/runner source after/' + name)
        for index, worker in enumerate(workers):
            for phase in ('before', 'after'):
                c.eq(worker['source_sha256_' + phase][name], {'original': archived, 'archive': archived}, f'{run.name}/p{index}/source {phase}/{name}')
        if name in EXPECTED:
            c.eq(archived, EXPECTED[name], run.name + '/frozen expected source/' + name)
        source_report[name] = {'archive': archived, 'current': current, 'recorded': entry['sha256']}
    c.check(len({w['pid'] for w in workers}) == 3, run.name + '/independent PIDs')
    byte_rows, process_details, public_inventories = [], [], []
    opened_pngs, author_cases, negatives = 0, 0, 0
    for index, worker in enumerate(workers):
        process = run / f'process-{index}'
        label = f'{run.name}/p{index}'
        raw = read(process / 'timings.unverified.json')
        publication_evidence = read(process / 'publication-evidence.json')
        consumed = read(process / 'consumption.json')
        c.eq(worker['process_index'], index, label + '/process index')
        c.check(worker['background'] and worker['shared_control_translate_identity'], label + '/background and control identity')
        c.eq(worker['module_names'], {'A': 'human_eye_fast._ao_A', 'R': 'human_eye_fast._ao_R'}, label + '/isolated modules')
        c.eq(worker['thread_environment'], manifest['thread_environment'], label + '/thread env')
        c.check(all(v == '1' for v in worker['thread_environment'].values()), label + '/single thread env')
        c.eq(worker['input_before'], worker['input_after'], label + '/raw fact hash unchanged')
        c.eq([len(s) for s in worker['input_before']], [20, 20], label + '/two full raw states')
        c.check(all(a != b for a, b in zip(*worker['input_before'])), label + '/every input state changes')
        c.check(worker['quality']['passed'] and not worker['quality']['failures'], label + '/quality result')
        c.eq(consumed['python_executable'], manifest['runner_executable'], label + '/Pillow scoring interpreter')
        c.check(consumed['pid'] != worker['pid'], label + '/scoring outside Blender process')
        c.check(consumed['passed'] and not consumed['failures'], label + '/saved scoring pass')
        actual_manifest = {str(path.relative_to(process)).replace('\\', '/'): {'bytes': path.stat().st_size, 'sha256': sha(path)}
                           for method in METHODS for path in sorted((process / f'method-{method}').rglob('*')) if path.is_file()}
        c.eq(actual_manifest, worker['public_artifacts'], label + '/all public files unchanged')
        public_inventories.append({k: v['sha256'] for k, v in actual_manifest.items()})
        schemas = {m: read(process / f'method-{m}/schema.json') for m in METHODS}
        c.eq(schemas['A'], schemas['R'], label + '/schema A R')
        c.eq(schemas['A'], schemas['D'], label + '/schema A D')
        outputs = {}
        for state in (0, 1):
            methods = {}
            canonical = {}
            for method in METHODS:
                public = process / f'method-{method}/state-{state}'
                for members in [list(range(1, 21)), *GROUPS.values()]:
                    outputs[(state, method, tuple(members))] = publications(public, method, members)
                metadata = outputs[(state, method, tuple(range(1, 21)))]
                c.eq(len(metadata['task_bytes']), 20, label + f'/s{state}/{method}/20 tasks')
                c.eq(len(metadata['publication_bytes']), 22, label + f'/s{state}/{method}/22 publications')
                methods[method] = metadata
                arm, suffix = ('baseline', 'b') if method == 'D' else ('candidate', 'c')
                canonical[method] = []
                for case in range(1, 21):
                    payload = (public / f'{case:02}.{suffix}.json').read_bytes()
                    package = decode(json.loads(payload), schemas[method])
                    c.eq(package['length_unit'], 'm', label + f'/s{state}/{method}/{case}/units')
                    canonical[method].append({k: v for k, v in package.items() if k != 'version'})
                    if case >= 19:
                        before = decode(read(public / f'{arm}-before-{case:02}.json'), schemas[method])
                        c.eq(before, {**package, 'observations': package['observations'][:1], 'outcome': None}, label + f'/s{state}/{method}/{case}/initial package')
                    if method == 'R':
                        c.eq(payload, (process / f'method-A/state-{state}/{case:02}.c.json').read_bytes(), label + f'/s{state}/{case}/A R final byte exact')
                        if case >= 19:
                            c.eq((public / f'candidate-before-{case:02}.json').read_bytes(), (process / f'method-A/state-{state}/candidate-before-{case:02}.json').read_bytes(), label + f'/s{state}/{case}/A R before byte exact')
                for path in sorted((public / 'images').glob('*.png')):
                    with Image.open(path) as image:
                        image.load()
                        c.eq(list(image.size), [1024, 512], label + '/' + method + '/' + path.name + '/PNG decode size')
                    opened_pngs += 1
                    peer = process / f'method-A/state-{state}/images/{path.name}'
                    c.eq(path.read_bytes(), peer.read_bytes(), label + f'/s{state}/{method}/{path.name}/identical PNG')
                    fixture_path = process / f'fixtures/state-{state}/images/{path.name}'
                    c.eq(path.read_bytes(), fixture_path.read_bytes(), label + f'/s{state}/{method}/{path.name}/fixture PNG')
                png_meta = {f'images/{p.name}': {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in sorted((public / 'images').glob('*.png'))}
                c.eq(png_meta, worker['fixtures'][state]['png'], label + f'/s{state}/{method}/PNG manifest')
                c.eq(sum(v['bytes'] for v in png_meta.values()), worker['fixtures'][state]['png_bytes'], label + f'/s{state}/{method}/PNG total')
            c.eq(canonical['A'], canonical['R'], label + f'/s{state}/A R all fields bit exact')
            c.eq(canonical['A'], canonical['D'], label + f'/s{state}/A D same information float64 bits')
            med = {m: statistics.median(methods[m]['task_bytes']) for m in METHODS}
            byte_rows.append({'process_index': index, 'pid': worker['pid'], 'state': state,
                              'task_bytes': {m: methods[m]['task_bytes'] for m in METHODS},
                              'publication_bytes': {m: methods[m]['publication_bytes'] for m in METHODS},
                              'total_bytes': {m: sum(methods[m]['task_bytes']) for m in METHODS},
                              'median_bytes': med, 'R_D_median_byte_ratio': med['R'] / med['D']})
        c.eq(len(consumed['conditions']), 6, label + '/six scored conditions')
        for condition, saved in zip(consumed['conditions'], publication_evidence['conditions']):
            method, state = condition['method'], condition['state']
            c.eq(condition['method'], saved['method'], label + '/scored method binding')
            c.eq(condition['state'], saved['state'], label + '/scored state binding')
            c.check(condition['passed'], label + '/condition passed')
            c.eq(len(condition['cases']), 20, label + '/20 scored tasks')
            for case, (row, evidence) in enumerate(zip(condition['cases'], saved['cases']), 1):
                author_cases += 1
                c.eq({k: row[k] for k in evidence}, evidence, label + f'/scoring source/{method}/{state}/{case}')
                c.check(row['passed'] and row['score']['passed'] and row['before_matches_actual_initial_publication'], label + f'/quality/{method}/{state}/{case}')
                actual_sizes = [v['bytes'] for v in outputs[(state, method, tuple(range(1, 21)))]['publications'] if v['case_id'] == f'{case:02}']
                c.eq(row['publication_bytes'], actual_sizes, label + f'/quality sizes/{method}/{state}/{case}')
                c.eq(row['bytes'], sum(actual_sizes), label + f'/quality task sum/{method}/{state}/{case}')
                for name, result in row.get('negative_controls', {}).items():
                    negatives += 1
                    c.check(result['rejected'], label + f'/negative/{method}/{state}/{case}/{name}')
        coverage = validate_series(c, worker['warmups'] + worker['samples'], raw['main'], list(range(1, 21)), 60, index, label + '/full', outputs)
        for group_index, (name, members) in enumerate(GROUPS.items()):
            rows = worker['groups'][name]['warmups'] + worker['groups'][name]['samples']
            validate_series(c, rows, raw['groups'][name], members, 24, index + group_index, label + '/' + name, outputs)
        c.eq(len(worker['cold']), 2, label + '/two cold states')
        for cold, unverified in zip(worker['cold'], raw['cold']):
            c.eq({k: v for k, v in cold.items() if k not in ('outputs', 'A_R_exact_bytes', 'same_as_state_reference')}, unverified, label + '/cold raw binding')
            for method in METHODS:
                c.check(type(cold['elapsed_ns'][method]) is int and cold['elapsed_ns'][method] > 0, label + '/cold duration')
                c.eq(cold['outputs'][method], outputs[(cold['state'], method, tuple(range(1, 21)))], label + '/cold publications')
        update = read(process / 'private/caller-update.json')
        c.eq(update, worker['caller_update'], label + '/caller update binding')
        c.check(update['passed'] and all(update['checks'].values()), label + '/caller update checks')
        c.check(update['input_digest_before'] != update['input_digest_after'], label + '/caller actual input changes')
        for method in METHODS:
            values = {}
            for phase in ('before', 'after'):
                path = process / f'private/caller-update-{method}-{phase}.json'
                c.eq(sha(path), update[phase + '_sha256'][method], label + f'/caller/{method}/{phase}/hash')
                values[phase] = decode(read(path), schemas[method])
                center = values[phase]['observations'][0]['deformation']['faces'][0]['position_m']
                c.eq(center, [2. if phase == 'before' else 3., 1., 0.], label + f'/caller/{method}/{phase}/centroid')
                c.eq(values[phase]['observations'][0]['objects'][0]['center_m'][0], -0., label + '/caller negative zero')
                c.check('中-👁' in values[phase]['object_ids'][0], label + '/caller unicode')
                if method == 'R':
                    c.eq(path.read_bytes(), (process / f'private/caller-update-A-{phase}.json').read_bytes(), label + f'/caller/{phase}/A R bytes')
            c.check(values['before'] != values['after'], label + '/caller output changes same input identity')
        process_details.append({'pid': worker['pid'], 'process_index': index, 'state_order_coverage': coverage,
                                'worker_sha256': sha(process / 'worker.json'), 'unverified_raw_sha256': sha(process / 'timings.unverified.json'),
                                'public_files': len(actual_manifest), 'scoring_pid': consumed['pid']})
    c.eq(opened_pngs, 126, run.name + '/126 PNG files decoded')
    c.eq(author_cases, 360, run.name + '/360 author scores')
    c.eq(negatives, 144, run.name + '/144 author negative controls')
    c.check(all(p == public_inventories[0] for p in public_inventories), run.name + '/public files identical across all three workers')
    c.eq(inventory(run), start_inventory, run.name + '/audit read-only source and outputs')
    return {'run': str(run), 'manifest_sha256': sha(run / 'source-manifest.json'), 'sources': source_report,
            'process_evidence': process_details, 'byte_rows': byte_rows, 'actual_png_files_opened': opened_pngs,
            'author_scores_checked': author_cases, 'negative_controls_checked': negatives,
            'all_formal_artifacts_sha256': start_inventory,
            'public_inventory_reference': public_inventories[0],
            'within_run_all_public_files_identical': all(p == public_inventories[0] for p in public_inventories)}, workers, claimed


def bundle(workers, byte_rows):
    rows = [r for w in workers for r in w['samples']]
    overall = recompute(rows)
    processes = [{'pid': w['pid'], 'process_index': w['process_index'], **recompute(w['samples'])} for w in workers]
    states = {str(state): recompute([r for r in rows if r['state'] == state]) for state in (0, 1)}
    groups = {name: recompute([r for w in workers for r in w['groups'][name]['samples']]) for name in GROUPS}
    group_states = {name: {str(state): recompute([r for w in workers for r in w['groups'][name]['samples'] if r['state'] == state]) for state in (0, 1)} for name in GROUPS}
    bootstrap = resample(workers)
    gates = {
        'pooled_R_A_median_le_0_95': overall['R_A_median_ratio'] <= .95,
        'pooled_R_A_p95_le_0_95': overall['R_A_p95_ratio'] <= .95,
        'each_process_R_A_median_le_0_95': all(p['R_A_median_ratio'] <= .95 for p in processes),
        'stratified_paired_median_difference_CI_upper_lt_zero': bootstrap['percentile_95_ci_ns'][1] < 0,
        'each_state_R_A_p95_le_1_05': all(v['R_A_p95_ratio'] <= 1.05 for v in states.values()),
        'each_group_R_A_p95_le_1_05': all(v['R_A_p95_ratio'] <= 1.05 for v in groups.values()),
        'original_R_D_p95_le_1_10': overall['R_D_p95_ratio'] <= 1.10,
        'original_each_state_median_bytes_R_D_le_0_70': all(v['R_D_median_byte_ratio'] <= .70 for v in byte_rows),
    }
    return {'overall': overall, 'per_process': processes, 'per_state': states,
            'groups_separate_from_main': groups, 'group_states_disclosure': group_states,
            'bootstrap': bootstrap, 'numeric_gates': gates, 'all_original_numeric_gates_met': all(gates.values())}


def verify_summary(c, recomputed, claimed, label):
    for key in ('overall', 'per_process', 'per_state', 'groups_separate_from_main', 'group_states_disclosure'):
        c.numeric(recomputed[key], claimed[key], label + '/' + key)
    for key in ('seed', 'replicates', 'strata_sizes', 'percentile_95_ci_ns'):
        c.numeric(recomputed['bootstrap'][key], claimed['bootstrap'][key], label + '/bootstrap/' + key)
    c.eq(recomputed['numeric_gates'], claimed['numeric_gates'], label + '/numeric gates')


def retained_attempts(parent, c):
    reports = []
    for directory in sorted(parent.glob('refinement_*')):
        exception_paths = sorted(directory.rglob('*exception*.json'))
        if not directory.is_dir() or not exception_paths:
            continue
        manifest_path = directory / 'source-manifest.json'
        c.check(manifest_path.exists(), directory.name + '/failed source manifest retained')
        manifest = read(manifest_path)
        for name, source in manifest['sources'].items():
            c.eq(sha(directory / source['archive']), source['sha256'], directory.name + '/failed archived source/' + name)
        raw = sorted(directory.glob('process-*/timings.unverified.json'))
        c.check(bool(raw), directory.name + '/failed raw timings retained')
        reports.append({'attempt': str(directory), 'source_manifest_sha256': sha(manifest_path),
                        'candidate_sha256': manifest['sources']['candidate']['sha256'],
                        'exceptions': {str(p.relative_to(directory)): read(p) for p in exception_paths},
                        'raw_timing_sha256': {str(p.relative_to(directory)): sha(p) for p in raw},
                        'formal_statistics_included': False})
    c.check(any(Path(r['attempt']).name == 'refinement_pilot_001' for r in reports), 'known failed first pilot preserved')
    return reports


def source_analysis(run, c):
    baseline_path = run / 'source/verification/baselines/ao_implementation.py'
    candidate_path = run / 'source/candidate.py'
    a, r = baseline_path.read_text(encoding='utf-8'), candidate_path.read_text(encoding='utf-8')
    def functions(source):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    fa, fr = functions(a), functions(r)
    changed = [name for name in fa if fa[name] != fr.get(name)]
    c.eq(set(fa), set(fr), 'source review/same public and helper functions')
    c.eq(changed, ['_deformation', '_json_bytes'], 'source review/only intended functions changed')
    c.check('check_circular=False' in r and '_ENCODER.encode(document).encode("utf-8")' in r, 'source review/static JSON config fresh encoding')
    bench = (run / 'source/verification/benchmark_ao_refinement.py').read_text(encoding='utf-8')
    c.check('project, json_bytes, version = module._project, module._json_bytes, module._BASELINE' in bench, 'source review/D shares R common improvements')
    c.check('before = type(package)((package.observations[0],))' in bench and 'return encode(before), encode(package)' in bench, 'source review/initial action package rebuilt inside batch')
    c.check('result = [_publications(encode, package) for package in packages]' in bench, 'source review/full timer includes original facts projection and publications')
    return {'changed_functions': changed,
            'diff': '\n'.join(difflib.unified_diff(a.splitlines(), r.splitlines(), fromfile='frozen A', tofile='candidate R')),
            'findings': [
                'R reuses only JSONEncoder configuration and disables circular detection for the trusted acyclic fact tree; every call still projects current raw facts and traverses them to new UTF8 bytes. No final-row, string, byte or observation-ID cache.',
                'Single-selected-face TD path fetches six scalar metrics and one triangle; centroid arithmetic order matches A. Zero-member and multiple-member paths retain prior behavior. Source schemas, object/frame/unit/witness/outcome associations stay unchanged.',
                'D binds the same R projection and JSON helper to descriptive named rows, so shared projection/configuration improvement is not exclusively attributed to R. A stays original hash.',
                'Action before wrappers are constructed anew inside each timer. All three calls in a group finish before validation, hashing, image reading or scoring; family samples and cold calls are separate from primary statistics.',
                'Control module is unchanged; no new runtime fallback/retry chain. Existing current-observation binding and stop-at-goal checks implement the serialized action contract.',
            ]}


def markdown(report):
    lines = ['# AO 二次优化独立原始证据审计', '',
             f"结论：**{report['decision']}**。检查 {report['checks']['count']:,} 项，异常 {len(report['checks']['errors'])} 项。独立读取源码、原样本和公开文件；未导入基准统计函数，未运行编码或性能采样。", '',
             '| 数据 | 三路组 | R/A 中位比 | R/A p95 比 | R/D p95 比 | 中位差 95% CI（ms） | 原数值门 |',
             '| --- | ---: | ---: | ---: | ---: | --- | --- |']
    for name, stats in report['statistics'].items():
        values = stats['overall']
        ci = [v / 1e6 for v in stats['bootstrap']['percentile_95_ci_ns']]
        lines.append(f"| {name} | {values['count']} | {values['R_A_median_ratio']:.6f} | {values['R_A_p95_ratio']:.6f} | {values['R_D_p95_ratio']:.6f} | [{ci[0]:.6f}, {ci[1]:.6f}] | {'通过' if stats['all_original_numeric_gates_met'] else '未通过'} |")
    lines.extend(['', '| 数据/进程 | PID | R/A 中位比 | R/A p95 比 |', '| --- | ---: | ---: | ---: |'])
    for name in ('initial', 'supplement'):
        for p in report['statistics'][name]['per_process']:
            lines.append(f"| {name}/{p['process_index']} | {p['pid']} | {p['R_A_median_ratio']:.6f} | {p['R_A_p95_ratio']:.6f} |")
    lines.extend(['', '首轮进程 0 的 p95 比值 1.147232（增加 14.7%）永久保留；原协议只对每个进程规定中位门，没有单独进程 p95 门。补测新增诊断门要求三个新进程 p95 比均 ≤ 1.05，结果单独列出。没有删除首测、挑选进程或重新加权。', '',
                  '较慢样本集中在一段连续调用中，多数同组三方法均高于各自中位水平。该记录不能证明 OS 调度或 GC 是原因；未记录这些事件，也不能保证未来不存在尾部代价。', '',
                  f"六个进程的公开文件跨进程、跨运行逐字节一致：{report['cross_run_public_byte_exact']}。每进程检查 {report['runs'][0]['process_evidence'][0]['public_files']} 个公开文件；A/R 所有 22 个出版包逐字节一致，D 恢复相同字段和 float64 位值，PNG/schema 单列。", '',
                  '20 题完整文字中位比为约 0.310658 / 0.312971，总字节 R 为 25,104 / 25,186，D 为 40,858 / 40,940。任务 19/20 的 before 和 final 均计入；读取并核对每个主样本、预热、家族样本与冷样本的逐包摘要及长度。', '',
                  '源码变化仅为 JSONEncoder 静态配置复用、可信无环树取消循环检测、TD 单面直接取指标。D 同样使用 R 的通用改进。输入更新探针保持包对象和观察 ID，修改实际借用数组后输出改变，旧 bytes 保持，负零和 Unicode 保留。', '',
                  '归档首个失败 pilot 的源码、原始计时与 Pillow 缺失错误均保留。该失败发生在计时后的图像评分，修正为父 Python 评分后使用新目录重测。', '',
                  '本文件不签发最终产品验收。公开单臂消费者与隔离评分结果由主对话单独核验；这些证据若绑定到完全一致的公开文件，可适用于六个进程。现场 Fact 对象没有完整序列化，输入不变性依据保存的前后内容摘要及已审源码，不能声称从原始内存独立重算。'])
    if report['checks']['errors']:
        lines.extend(['', '异常：', *('- ' + error for error in report['checks']['errors'])])
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=lambda p: Path(p).resolve())
    parser.add_argument('--supplement', required=True, type=lambda p: Path(p).resolve())
    parser.add_argument('--output', required=True, type=lambda p: Path(p).resolve())
    args = parser.parse_args()
    text_path = args.output.with_suffix('.md')
    if args.output.exists() or text_path.exists():
        parser.error('Output exists; retain prior audit and choose a fresh output path.')
    c = Checks()
    initial, iw, initial_claimed = audit_run(args.run, c)
    supplemental, sw, supplement_claimed = audit_run(args.supplement, c)
    for name, item in initial['sources'].items():
        c.eq(item['archive'], supplemental['sources'][name]['archive'], 'cross-run/source/' + name)
    public_equal = initial['public_inventory_reference'] == supplemental['public_inventory_reference']
    c.check(public_equal, 'all public bytes identical across runs and all six workers')
    c.check(len({w['pid'] for w in iw + sw}) == 6, 'six independent Blender PIDs')
    primary_stats = bundle(iw, initial['byte_rows'])
    supplement_stats = bundle(sw, supplemental['byte_rows'])
    combined_stats = bundle(iw + sw, initial['byte_rows'] + supplemental['byte_rows'])
    verify_summary(c, primary_stats, initial_claimed, 'initial independently recomputed summary')
    verify_summary(c, supplement_stats, supplement_claimed, 'supplement independently recomputed summary')
    diagnostic = all(p['R_A_p95_ratio'] <= 1.05 for p in supplement_stats['per_process'])
    plan = args.run.parent / 'refinement_supplement_plan.md'
    c.check(plan.exists(), 'supplement plan retained')
    failed = retained_attempts(args.run.parent, c)
    source_review = source_analysis(args.run, c)
    passed = not c.errors and all(s['all_original_numeric_gates_met'] for s in (primary_stats, supplement_stats, combined_stats)) and diagnostic
    report = {
        'decision': 'RAW_SOURCE_STATISTICS_PASS_ROOT_ACCEPTANCE_SEPARATE' if passed else 'FAIL_AUDIT_OR_FROZEN_GATE',
        'final_acceptance_issued': False,
        'checks': {'count': c.count, 'errors': c.errors, 'passed': not c.errors},
        'runs': [initial, supplemental], 'statistics': {'initial': primary_stats, 'supplement': supplement_stats, 'combined': combined_stats},
        'supplement_diagnostic_each_process_p95_le_1_05': diagnostic,
        'supplement_plan': {'path': str(plan), 'sha256': sha(plan), 'text': plan.read_text(encoding='utf-8')},
        'cross_run_public_byte_exact': public_equal,
        'initial_process0_tail': tail_disclosure(iw[0]),
        'source_analysis': source_review, 'retained_failed_attempts': failed,
        'audit_source_sha256': sha(__file__),
        'limitations': [
            'This source/raw/three-arm audit is separate from the root blind public consumer; it does not issue final engine acceptance.',
            'Raw-fact before/after content hashes and source algorithm checked, but full live Fact objects were not persisted; cannot independently reconstruct those exact raw-memory digests.',
            'Each hot publication hash is bound to actual saved reference files; exact runtime equality assertions were reviewed. Individual identical hot byte strings are not all stored separately.',
            'First-process p95 regression remains disclosed. Its cause is unproven; co-occurring slow groups do not prove OS scheduling or GC.',
            'Cold entries exclude imports/scenes and share R/D helpers; they are not process-startup latency. PNG and schema are excluded from text ratios and reported separately.',
            'No external-model, token/cost or full-engine end-to-end improvement has been measured here.',
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
    with text_path.open('x', encoding='utf-8') as stream:
        stream.write(markdown(report))
    print(json.dumps({'decision': report['decision'], 'checks': report['checks'],
                      'statistics': {k: {**v['overall'], 'CI_ns': v['bootstrap']['percentile_95_ci_ns']} for k, v in report['statistics'].items()},
                      'supplement_diagnostic': diagnostic, 'cross_run_public_byte_exact': public_equal}, indent=2))
    return int(not passed)


if __name__ == '__main__':
    raise SystemExit(main())
