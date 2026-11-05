"""Independent archived AO evidence audit; no producer imports or performance runs.

This cross-arm/private evidence audit complements, but is not, a blind public consumer.
Original raw evidence is never edited. The requested audit destination must be new.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import statistics
import struct
import sys

import numpy as np
from PIL import Image

ARMS = ('candidate', 'baseline')
SUFFIX = {'candidate': 'c', 'baseline': 'b'}
METRICS = ('max_principal_stretch', 'min_principal_stretch', 'max_area_strain',
           'max_normal_angle_deg', 'max_centroid_displacement', 'score')
CHILDREN = {
    'package': {'observations': ('observation', True), 'outcome': ('outcome', False)},
    'observation': {'objects': ('object', True), 'clearance': ('clearance', False),
                    'deformation': ('deformation', False), 'image': ('image', False)},
    'clearance': {'witness_a': ('witness', False), 'witness_b': ('witness', False)},
    'deformation': {'faces': ('face', True)},
    'image': {'section': ('section', False), 'global_view': ('view', False), 'local_view': ('view', False)},
    'outcome': {'goal': ('goal', False), 'command': ('command', False)},
}


def load(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, float):
        return struct.pack('>d', left) == struct.pack('>d', right)
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    return left == right


class Checks:
    def __init__(self):
        self.count = 0
        self.errors = []

    def check(self, result, label):
        self.count += 1
        if not result:
            self.errors.append(label)

    def equal(self, left, right, label):
        self.check(same(left, right), label)

    def close(self, left, right, label, atol=1e-12):
        self.check(np.allclose(left, right, atol=atol, rtol=0), label)


def decode(value, schema, kind='package'):
    if value is None:
        return None
    columns = schema['columns'][kind]
    if isinstance(value, list):
        if len(value) != len(columns):
            raise ValueError((kind, 'column count'))
        row = dict(zip(columns, value))
    elif isinstance(value, dict) and set(value) == set(columns):
        row = dict(value)
    else:
        raise ValueError((kind, 'fields'))
    for field, (child, many) in CHILDREN.get(kind, {}).items():
        row[field] = [decode(x, schema, child) for x in row[field]] if many else decode(row[field], schema, child)
    return row


def point_on_triangle(point, triangle):
    triangle = np.asarray(triangle, dtype=float)
    delta = np.asarray(point) - triangle[0]
    edges = (triangle[1:] - triangle[0]).T
    uv = np.linalg.lstsq(edges, delta, rcond=None)[0]
    return (np.linalg.norm(edges @ uv - delta) <= 1e-9
            and min(uv) >= -1e-7 and sum(uv) <= 1 + 1e-7)


def clearance(c, public, truth, ids, label):
    c.equal([ids[i] for i in public['target_object_indices']], truth['target_ids'], label + '/targets')
    c.equal(public['distance_m'], truth['distance_m'], label + '/distance float64')
    distance = truth['distance_m']
    c.equal(public['status'], 'empty_surface' if distance is None else 'positive_gap' if distance > 0 else 'zero_distance', label + '/status')
    if distance is None:
        c.check(public['witness_a'] is None and public['witness_b'] is None, label + '/empty witnesses')
        return
    if truth.get('analytic_distance_m') is not None:
        c.close(distance, truth['analytic_distance_m'], label + '/analytic distance', truth['analytic_tol_m'])
    for end in ('a', 'b'):
        witness = public['witness_' + end]
        face = witness['original_face_id']
        c.equal(face, truth['triangle_' + end], label + '/' + end + '/original face')
        c.equal(witness['point_m'], truth['point_' + end], label + '/' + end + '/point float64')
        c.check(point_on_triangle(witness['point_m'], truth['triangles_' + end][face]), label + '/' + end + '/independent barycentric')
    c.close(np.linalg.norm(np.array(public['witness_a']['point_m']) - public['witness_b']['point_m']), distance, label + '/witness norm', 1e-9)


def facts(c, package, truth, public_dir, images, label):
    c.equal(package['length_unit'], 'm', label + '/units')
    ids = package['object_ids']
    c.check(len(ids) == len(set(ids)), label + '/unique ids')
    c.equal(len(package['observations']), len(truth['observations']), label + '/observation count')
    for index, (obs, expected) in enumerate(zip(package['observations'], truth['observations'])):
        tag = label + '/obs' + str(index)
        for key in ('observation_id', 'frame_id'):
            c.equal(obs[key], expected[key], tag + '/' + key)
        actual_objects = {ids[obj['object_index']]: {k: obj[k] for k in ('topology_generation', 'center_m')} for obj in obs['objects']}
        c.equal(actual_objects, expected['objects'], tag + '/objects')
        for field in ('clearance', 'deformation', 'image'):
            c.check((obs[field] is None) == (expected[field] is None), tag + '/' + field + '/presence')
        if obs['clearance']:
            clearance(c, obs['clearance'], expected['clearance'], ids, tag + '/clearance')
        if obs['deformation']:
            td, et = obs['deformation'], expected['deformation']
            c.equal(ids[td['object_index']], et['object_id'], tag + '/TD object')
            for key in ('reference_frame', 'sample_frames', 'reduced_face_count', 'top_face_ids', 'position_kind', 'position_frame'):
                c.equal(td[key], et[key], tag + '/TD/' + key)
            c.equal(len(td['faces']), len(et['faces']), tag + '/TD member count')
            for face, ef in zip(td['faces'], et['faces']):
                for key in ('original_face_id', *METRICS):
                    c.equal(face[key], ef[key], tag + '/TD/' + str(face['original_face_id']) + '/' + key)
                c.close(face['position_m'], ef['position_m'], tag + '/TD centroid')
                analytic_position = et.get('analytic_positions_m', {}).get(str(face['original_face_id']))
                if analytic_position is not None:
                    c.close(face['position_m'], analytic_position, tag + '/TD analytic world position')
                for key, value in et.get('analytic_metrics', {}).get(str(face['original_face_id']), {}).items():
                    if value is None:
                        c.check(face[key] is None, tag + '/TD undefined ' + key)
                    else:
                        c.close(face[key], value, tag + '/TD analytic ' + key, 1e-10)
            if 'analytic_top_face_ids' in et:
                c.equal(td['top_face_ids'], et['analytic_top_face_ids'], tag + '/TD analytic top IDs')
        if obs['image']:
            img, et = obs['image'], expected['image']
            meta = et['metadata']
            c.equal(img['path'], et['path'], tag + '/PNG path')
            path = public_dir / img['path']
            if str(path) not in images:
                with Image.open(path) as png:
                    png.load()
                    c.equal(list(png.size), [1024, 512], tag + '/actual PNG size')
                images[str(path)] = {'bytes': path.stat().st_size, 'sha256': sha(path)}
            c.equal(images[str(path)]['sha256'], et['png_sha256'], tag + '/PNG hash')
            c.equal([img['width_px'], img['height_px']], [1024, 512], tag + '/published PNG size')
            c.equal(obs['frame_id'], meta['frame_id'], tag + '/VG frame')
            for key in ('meters_per_blender_unit', 'mode', 'section'):
                c.equal(img[key], meta[key], tag + '/VG/' + key)
            for field, key in (('target_object_indices', 'target_ids'), ('mesh_object_indices', 'mesh_ids')):
                c.equal([ids[i] for i in img[field]], meta[key], tag + '/VG/' + key)
            for view in ('global', 'local'):
                actual, ev = img[view + '_view'], meta['views'][view]
                mapped = {'viewport': ev['viewport'], 'camera_type': ev['rna']['type']}
                for dst, src in [('matrix_world_blender', 'matrix_world'), ('ortho_scale_blender', 'ortho_scale'), ('clip_start_blender', 'clip_start'), ('clip_end_blender', 'clip_end'), ('shift_x', 'shift_x'), ('shift_y', 'shift_y'), ('projection_blender', 'projection')]:
                    mapped[dst] = ev['rna'][src]
                for key in ('view', 'projection', 'view_projection'):
                    mapped['gpu_' + key + '_m'] = ev['gpu'][key]
                c.equal(actual, mapped, tag + '/actual camera/' + view)
    outcome = package['outcome']
    c.check((outcome is None) == (truth['outcome'] is None), label + '/outcome presence')
    if outcome:
        actual = dict(outcome)
        goal = dict(outcome['goal'])
        goal['moving_id'] = ids[goal.pop('moving_object_index')]
        goal['reference_id'] = ids[goal.pop('reference_object_index')]
        actual['goal'] = goal
        c.equal(actual, truth['outcome'], label + '/real outcome transport')
        before, after = package['observations']
        c.equal([outcome['before_observation_id'], outcome['after_observation_id']], [before['observation_id'], after['observation_id']], label + '/action observation binding')
        c.equal(outcome['measured_delta_m'], after['clearance']['distance_m'] - before['clearance']['distance_m'], label + '/measured delta')
        c.equal(outcome['goal_reached'], abs(outcome['distance_after_m'] - goal['target_distance_m']) <= goal['tolerance_m'], label + '/actual goal')


def native_actions(c, rows, schema):
    c.equal([row['case_id'] for row in rows], [f'T{i:02}' for i in range(1, 21)], 'native/20 fixed cases')
    records = []
    for row in rows:
        label = 'native/' + row['case_id']
        outcome = row['outcome']
        goal, action = outcome['goal'], outcome['action']
        moving, reference = goal['moving_id'], goal['reference_id']
        command = action['command']
        scale = row['meters_per_blender_unit']
        before_public, after_public = (decode(row[k], schema) for k in ('public_before', 'public_after'))
        c.equal(before_public['observations'], after_public['observations'][:1], label + '/immutable before')
        c.equal(before_public['outcome'], None, label + '/before no outcome')
        for phase, public in (('before', before_public['observations'][0]), ('after', after_public['observations'][1])):
            snapshot = row['native_' + phase]
            native = snapshot[moving]
            actual_control = (np.asarray(native['matrix_world_blender'])[:3, 3] * scale).tolist() if 'delta_world_m' in command else native['key_value']
            c.equal(actual_control, outcome['control_' + phase], label + '/' + phase + '/native control')
            surface = outcome[phase]['surface']
            truth = {'target_ids': outcome[phase]['target_ids'], **surface,
                     'analytic_distance_m': row['expected_distance_' + phase + '_m'],
                     'analytic_tol_m': goal['tolerance_m']}
            for end, object_id in zip(('a', 'b'), truth['target_ids']):
                mesh = snapshot[object_id]
                truth['triangles_' + end] = np.asarray(mesh['world_vertices_m'])[mesh['triangles']].tolist()
            clearance(c, public['clearance'], truth, after_public['object_ids'], label + '/' + phase)
            c.equal(public['observation_id'], outcome[phase]['observation_id'], label + '/' + phase + '/observation')
        if 'delta_world_m' in command:
            c.close(np.asarray(outcome['control_after']) - outcome['control_before'], command['delta_world_m'], label + '/world delta with units and parent', goal['tolerance_m'])
            c.close(np.asarray(row['native_after'][moving]['world_vertices_m']) - row['native_before'][moving]['world_vertices_m'], command['delta_world_m'], label + '/native vertex displacement', goal['tolerance_m'])
            c.close(np.asarray(row['native_before'][moving]['matrix_world_blender'])[:3, :3], np.asarray(row['native_after'][moving]['matrix_world_blender'])[:3, :3], label + '/linear transform preserved', 3e-6)
        else:
            c.equal(outcome['control_after'], command['value'], label + '/evaluated shape target')
            c.check(row['native_before'][moving]['world_vertices_m'] != row['native_after'][moving]['world_vertices_m'], label + '/shape changed actual vertices')
            expected_delta = np.zeros_like(row['native_before'][moving]['world_vertices_m'])
            expected_delta[0, 0] = .003 * (command['value'] - row['native_before'][moving]['key_value'])
            c.close(np.asarray(row['native_after'][moving]['world_vertices_m']) - row['native_before'][moving]['world_vertices_m'], expected_delta, label + '/only bound tip deforms', goal['tolerance_m'])
        c.equal(row['native_before'][reference], row['native_after'][reference], label + '/unchanged reference in fixed matrix')
        initial, final = (outcome[p]['surface']['distance_m'] for p in ('before', 'after'))
        c.equal(outcome['measured_delta_m'], final - initial, label + '/measured not predicted')
        c.equal(outcome['goal_reached'], abs(final - goal['distance_m']) <= goal['tolerance_m'], label + '/goal actual')
        c.equal(row['terminal_probe_zero_write'], True, label + '/terminal executed assertion evidence')
        encoded = after_public['outcome']
        for key in ('control_before', 'control_after', 'measured_delta_m', 'goal_reached'):
            c.equal(encoded[key], outcome[key], label + '/published/' + key)
        c.equal(encoded['predicted_delta_m'], action['predicted_delta_m'], label + '/prediction remains separate')
        records.append({'case_id': row['case_id'], 'unit_scale': scale, 'command': command,
                        'distance_before_m': initial, 'distance_after_m': final,
                        'parented': 'parent_matrix_world_blender' in row['native_before'][moving],
                        'terminal_evidence': 'saved boolean plus archived test assertion; terminal snapshot not separately retained'})
    return records


def p95(values):
    return float(np.quantile(values, .95, method='linear'))


def timing(rows):
    values = {arm: [r['elapsed_ns'][arm] for r in rows] for arm in ARMS}
    result = {'count': len(rows), 'median_ns': {a: statistics.median(v) for a, v in values.items()},
              'p95_ns': {a: p95(v) for a, v in values.items()},
              'paired_delta_median_ns': statistics.median(r['elapsed_ns']['candidate'] - r['elapsed_ns']['baseline'] for r in rows)}
    result['p95_ratio'] = result['p95_ns']['candidate'] / result['p95_ns']['baseline']
    return result


REVIEWED_BENCHMARKS = {
    '86b872abe24320d4cd23479634544d0dbfdd36eec3c84d58b3cb378a815320ea': 20,
    '944721c519513a5d17565ec8c5795433ffc00b872f7c5a980986a92d8566fb3c': 22,
}
REVIEWED_CORE = {
    'human_eye_fast/fast_affordance_out.py': '5d8f3982d79af6e276e2da178b7707f1513508bdd14626089006e4900c1676bf',
    'human_eye_fast/control.py': 'd6c81d30f10fa70de7d371191224d322cc1acbf5a13ddbddeb7c86c51ae7c1a8',
    'verification/ao_fixtures.py': '419b87da8d1792faf5756b86e579f2833c951b98600c07a93cab81713ad1749c',
    'verification/test_blender_control.py': '3926ca3d4eaf821ea0c8d1aa1b0c4e3195975f9ecf7f14a070bcb0aa1f5f99ec',
    'verification/test_fast_affordance_out.py': '93a884b4aa3b3f854866b1d251546e557ca26b67e8083229334fde0668959de3',
    'docs/AO_ACCEPTANCE_PROTOCOL.md': '1832030ea83bc22c1111909567510bdfd41df5fd8f54c814341d3f9c310f7fc5',
}


def audit(run, previous=None):
    c = Checks()
    manifest, summary = load(run / 'source-manifest.json'), load(run / 'summary.json')
    source = {}
    for name, expected in manifest['sha256'].items():
        path = run / 'source' / name
        actual = sha(path)
        c.equal(actual, expected, 'source/archive hash/' + name)
        source[name] = {'sha256': actual, 'matches_manifest': actual == expected}
        if name.endswith('.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            source[name]['functions'] = {node.name: node.lineno for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        if name in REVIEWED_CORE:
            c.equal(actual, REVIEWED_CORE[name], 'source/reviewed core/' + name)
    benchmark = 'verification/benchmark_fast_affordance_out.py'
    encoded_count = REVIEWED_BENCHMARKS.get(source[benchmark]['sha256'])
    c.check(encoded_count in (20, 22), 'source/benchmark must have independent source review')
    complete = encoded_count == 22
    expected_order = [f'{i:02}-{phase}' for i in range(1, 21) for phase in (('before', 'final') if i >= 19 else ('final',))]
    images, public_hashes, processes, all_samples, all_states, negatives = {}, {}, [], [], [], []
    workers = [load(run / f'process-{i}' / 'worker.json') for i in range(3)]
    c.check(len({w['pid'] for w in workers}) == 3, '3 independent PIDs')
    schema_bytes = (run / 'process-0/schema.json').read_bytes()
    for process_index, worker in enumerate(workers):
        process = run / f'process-{process_index}'
        schema = load(process / 'schema.json')
        consumption = load(process / 'consumption.json')
        c.equal((process / 'schema.json').read_bytes(), schema_bytes, 'shared schema/' + str(process_index))
        c.equal(worker['process_index'], process_index, 'worker index/' + str(process_index))
        c.check(worker['background'], 'background Blender/' + str(process_index))
        c.equal(worker['thread_environment'], manifest['thread_environment'], 'thread env/' + str(process_index))
        c.equal(len(worker['warmups']), 5, '5 warmups/' + str(process_index))
        c.equal(len(worker['samples']), 31, '31 pairs/' + str(process_index))
        if complete:
            c.equal(worker['publication_order'], expected_order, 'publication order/' + str(process_index))
        state_lengths, state_publications, state_finals, state_hashes = [], [], [], []
        for state in range(2):
            public = process / f'state-{state}'
            oracle = load(process / 'private' / f'state-{state}-oracle.json')
            task_rows = load(public / 'tasks.json')
            c.equal(len(task_rows), 20, f'p{process_index}s{state}/20 tasks')
            lengths, publications, final_lengths, hashes = ({a: [] for a in ARMS} for _ in range(4))
            case_rows = []
            for case in range(1, 21):
                tag = f'p{process_index}s{state}/{case:02}'
                decoded, publication_record = {}, {}
                for arm in ARMS:
                    path = public / f'{case:02}.{SUFFIX[arm]}.json'
                    payload = path.read_bytes()
                    raw = json.loads(payload)
                    c.equal(json.dumps(raw, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode(), payload, tag + '/' + arm + '/compact UTF8')
                    package = decode(raw, schema)
                    c.equal(package['version'], schema['versions'][arm], tag + '/' + arm + '/version')
                    facts(c, package, oracle[case - 1], public, images, tag + '/' + arm)
                    decoded[arm] = package
                    final_lengths[arm].append(len(payload))
                    hashes[arm].append(sha(path))
                    public_hashes[str(path.relative_to(run))] = sha(path)
                    calls = []
                    if case >= 19:
                        before_path = public / f'{arm}-before-{case:02}.json'
                        before = decode(load(before_path), schema)
                        c.equal(before, {**package, 'observations': package['observations'][:1], 'outcome': None}, tag + '/' + arm + '/actual first publication')
                        calls.append({'phase': 'before', 'path': str(before_path.relative_to(run)), 'bytes': before_path.stat().st_size, 'in_timed_batch': complete})
                        public_hashes[str(before_path.relative_to(run))] = sha(before_path)
                    calls.append({'phase': 'final', 'path': str(path.relative_to(run)), 'bytes': len(payload), 'in_timed_batch': True})
                    publication_record[arm] = calls
                    sizes = [call['bytes'] for call in calls]
                    lengths[arm].append(sum(sizes))
                    publications[arm].extend(sizes)
                    report_case = consumption['states'][state]['cases'][case - 1]
                    reported = report_case['arms'][arm]
                    c.equal(reported['bytes'], sum(sizes) if complete else len(payload), tag + '/' + arm + '/reported bytes binding')
                    c.check(reported['score']['passed'], tag + '/' + arm + '/author score evidence')
                    for kind, control in report_case.get('negative_controls', {}).get(arm, {}).items():
                        negatives.append({'process': process_index, 'state': state, 'case': case, 'arm': arm, 'kind': kind, 'rejected': control['rejected']})
                        c.check(control['rejected'], tag + '/' + arm + '/recorded negative/' + kind)
                c.equal({k: v for k, v in decoded['candidate'].items() if k != 'version'}, {k: v for k, v in decoded['baseline'].items() if k != 'version'}, tag + '/same fields and float64 bits')
                case_rows.append({'case_id': f'{case:02}', 'publications': publication_record, 'total_bytes': {a: lengths[a][-1] for a in ARMS}})
            medians = {a: statistics.median(lengths[a]) for a in ARMS}
            report = {'process': process_index, 'state': state, 'cases': case_rows, 'actual_encode_calls': 22,
                      'full_task_median_bytes': medians, 'full_task_total_bytes': {a: sum(lengths[a]) for a in ARMS},
                      'full_task_median_ratio': medians['candidate'] / medians['baseline'],
                      'final_only_total_bytes': {a: sum(final_lengths[a]) for a in ARMS}}
            c.check(report['full_task_median_ratio'] <= .70, f'p{process_index}s{state}/byte gate')
            all_states.append(report)
            state_lengths.append(lengths)
            state_publications.append(publications)
            state_finals.append(final_lengths)
            state_hashes.append(hashes)
            actual_pngs = {str(Path(p).relative_to(public)).replace('\\', '/'): data for p, data in images.items() if Path(p).is_relative_to(public)}
            c.equal(actual_pngs, worker['states'][state]['png'], f'p{process_index}s{state}/PNG bytes and hashes')
            c.equal(sum(p['bytes'] for p in actual_pngs.values()), worker['states'][state]['png_bytes'], f'p{process_index}s{state}/PNG total')
        c.check(all(a != b for arm in ARMS for a, b in zip(state_hashes[0][arm], state_hashes[1][arm])), f'p{process_index}/every task differs across states')
        for sequence, sample in enumerate(worker['warmups'] + worker['samples']):
            tag = f'p{process_index}/sample{sequence}'
            state = sequence % 2
            c.equal(sample['sequence'], sequence, tag + '/sequence')
            c.equal(sample['state'], state, tag + '/alternating state')
            c.equal(sample['order'], list(ARMS if (sequence // 2 + process_index) % 2 == 0 else ARMS[::-1]), tag + '/state decoupled ABBA')
            for arm in ARMS:
                c.check(isinstance(sample['elapsed_ns'][arm], int) and sample['elapsed_ns'][arm] > 0, tag + '/' + arm + '/elapsed')
                c.equal(sample['bytes'][arm], (state_lengths if complete else state_finals)[state][arm], tag + '/' + arm + '/timed byte counts')
                if complete:
                    c.equal(sample['publication_bytes'][arm], state_publications[state][arm], tag + '/' + arm + '/22 timed publications')
        c.check({(s['state'], tuple(s['order'])) for s in worker['samples']} == {(s, o) for s in (0, 1) for o in (ARMS, ARMS[::-1])}, f'p{process_index}/both orders both states')
        snapshot = load(process / 'private/rb-snapshot.json')
        for arm in ARMS:
            old, new = (decode(snapshot[arm][k], schema) for k in ('old', 'new'))
            c.equal(old['observations'][0]['deformation']['faces'][0]['position_m'], [2., 1., 0.], f'p{process_index}/{arm}/old borrowed snapshot')
            c.equal(new['observations'][0]['deformation']['faces'][0]['position_m'], [3., 1., 0.], f'p{process_index}/{arm}/new borrowed snapshot')
            c.equal([old['observations'][0]['frame_id'], new['observations'][0]['frame_id']], [8, 9], f'p{process_index}/{arm}/snapshot frames')
        process_timing = timing(worker['samples'])
        processes.append({'process_index': process_index, 'pid': worker['pid'], 'timing': process_timing,
                          'state_timings': {str(s): timing([r for r in worker['samples'] if r['state'] == s]) for s in (0, 1)}})
        for metric in ('median_ns', 'p95_ns'):
            for arm in ARMS:
                c.close(process_timing[metric][arm], summary['per_process'][process_index][metric][arm], f'p{process_index}/summary/' + metric + '/' + arm, 1e-6)
        all_samples.extend(worker['samples'])
    pooled = timing(all_samples)
    for arm in ARMS:
        c.close(pooled['p95_ns'][arm], summary['p95_encoding_batch_ns'][arm], 'summary/pooled p95/' + arm, 1e-6)
    c.close(pooled['p95_ratio'], summary['p95_encoding_ratio'], 'summary/pooled p95 ratio', 1e-14)
    c.equal(len(all_samples), 93, '93 independent paired batches')
    c.equal(len(images), 42, '42 actual unique PNGs loaded')
    c.equal(len(negatives), 96, '96 recorded negative controls')
    c.equal(len(schema_bytes), summary['shared_schema_bytes'], 'separate schema cost')
    actions = native_actions(c, load(run / 'process-0/private/actions.json'), load(run / 'process-0/schema.json'))
    comparison = None
    if previous:
        old_manifest = load(previous / 'source-manifest.json')
        same_core = all(old_manifest['sha256'][name] == manifest['sha256'][name] for name in REVIEWED_CORE)
        c.check(same_core, 'previous run/core source unchanged')
        old_paths = []
        for index in range(3):
            old_paths.extend((previous / f'process-{index}').glob('schema.json'))
            for state in range(2):
                old_paths.extend(p for p in (previous / f'process-{index}/state-{state}').rglob('*') if p.is_file())
        unchanged = all(sha(path) == sha(run / path.relative_to(previous)) for path in old_paths)
        c.check(unchanged, 'previous run/all public files unchanged')
        comparison = {'previous': str(previous), 'core_source_unchanged': same_core,
                      'public_files_compared': len(old_paths), 'all_public_bytes_identical': unchanged}
    batch_source = (run / 'source' / benchmark).read_text(encoding='utf-8')
    fixture_source = (run / 'source/verification/ao_fixtures.py').read_text(encoding='utf-8')
    c.check('action_delivery_ns' in fixture_source and 'before_package' in fixture_source and 'baseline_action_delivery_ns' in fixture_source, 'source/real initial publication exists in both arms')
    c.check('assert {name: _sha(ROOT / name) for name in SOURCES} == sources' in batch_source, 'source/end-to-end source hash assertion')
    regression = run / 'native-action-regression.log'
    if not regression.exists() and previous:
        regression = previous / 'native-action-regression.log'
    regression_evidence = None
    if regression.exists():
        log = regression.read_text(encoding='utf-8')
        for name in ('test_fixed_action_matrix', 'test_stale_observation_cannot_issue_action', 'test_empty_surface_never_labels_measured_distance', 'test_moving_reference_and_prediction_do_not_define_goal_result'):
            c.check(any(name in line and line.endswith(' ... ok') for line in log.splitlines()), 'native regression/' + name)
        c.check('Ran 4 tests' in log and '\nOK\n' in log, 'native regression/completed')
        regression_evidence = {'path': str(regression), 'sha256': sha(regression), 'test_count': 4,
                               'scope': 'Historical executed regression log; same archived control/test source. Not a new native run by auditor.'}
    batch_tree = ast.parse(batch_source)
    source_functions = {n.name: ast.get_source_segment(batch_source, n) for n in batch_tree.body if isinstance(n, ast.FunctionDef)}
    if complete:
        c.check('before = type(package)((package.observations[0],))' in source_functions['_encode_publications'], 'source/before package assembled each call')
        c.check('return encode(before), encode(package)' in source_functions['_encode_publications'], 'source/two action encoder calls')
        c.check('result = [_encode_publications(encode, package) for package in packages]' in source_functions['_encode_batch'], 'source/timed full publications')
        c.equal(summary['publications_per_batch'], 22, 'summary/full batch size')
    decision = 'REWORK_TIMING_BOUNDARY' if not complete else 'SOURCE_STATISTICS_QUALITY_PASS_PENDING_PUBLIC_CONSUMER'
    if c.errors:
        decision = 'FAIL_INDEPENDENT_AUDIT'
    numeric = pooled['p95_ratio'] <= 1.10
    if complete and not numeric:
        decision = 'FAIL_ENCODING_P95'
    report = {
        'run': str(run), 'decision': decision, 'implementation_layer_accepted': False,
        'acceptance_scope': 'Private/cross-arm implementation source and raw evidence audit. Root blind public consumer and root final acceptance remain separate.',
        'checks': {'count': c.count, 'errors': c.errors, 'passed': not c.errors},
        'source_archive': source, 'manifest_sha256': sha(run / 'source-manifest.json'),
        'summary_sha256': sha(run / 'summary.json'), 'audit_source_sha256': sha(__file__),
        'source_binding_scope': 'All archived source hashes verified. Runner copies source before workers and asserts live hashes unchanged after all workers. Workers record independent PIDs but not individual before/after source hashes.',
        'encoding_boundary': {'tasks': 20, 'actual_publications': 22, 'measured_publications': encoded_count,
                              'complete': complete, 'final_only_measurements_not_relabelled': not complete,
                              'full_batch_p95_ratio': pooled['p95_ratio'] if complete else None,
                              'missing_calls': [] if complete else ['19-before', '20-before'],
                              'initial_packets_also_inside_final': True,
                              'same_fact_inputs_both_arms': True, 'no_final_byte_cache_in_reviewed_source': True,
                              'timed_function_source': source_functions['_encode_batch'],
                              'timed_publication_function_source': source_functions.get('_encode_publications')},
        'measured_timing': pooled, 'processes': processes, 'actual_transmissions_by_process_state': all_states,
        'gates_within_audit_scope': {'source_raw_quality_evidence': not c.errors,
                                   'actual_20_task_median_byte_ratio_le_0_70': all(s['full_task_median_ratio'] <= .70 for s in all_states),
                                   'complete_22_publication_batch': complete,
                                   'complete_batch_p95_le_1_10': complete and numeric},
        'schema': {'bytes_once': len(schema_bytes), 'sha256': hashlib.sha256(schema_bytes).hexdigest()},
        'png': {'unique_files_opened': len(images), 'files': images,
                'bytes_by_process_state': [[w['states'][s]['png_bytes'] for s in (0, 1)] for w in workers]},
        'native_actions': actions, 'native_regression': regression_evidence, 'negative_controls': negatives,
        'public_artifact_sha256': public_hashes, 'previous_run_comparison': comparison,
        'architecture_algorithm_findings': [
            'Fair baseline uses the exact same _project on same original facts, with compact descriptive dictionaries versus candidate fixed-column rows. Both select TD faces and centroids, build object indices, attach BC/VG/Outcome and encode shortest roundtrip JSON in the timer.',
            'No byte/result memoization. Reference bytes are used only for equality after both timed arms. Two actual different fact states alternate; every task changes and each state covers both orders.',
            'Rows preserve original face IDs, full sample frames versus selected faces, undefined metrics, positive microgap and unsigned zero distance. Public image matrices retain actual RNA/GPU camera values; PNG and schema cost are separate.',
            'Controller acts on current observation, handles meter/world transform and parented objects, re-evaluates depsgraph, captures both objects, updates BC, measures actual outcome, and stops before a write when goal is already reached.',
            'Borrowed RB geometry stays mutable until encoding; returned bytes detach scalars. Current synchronous observation/action contract is serial; frozen dataclass alone does not deep-freeze future borrowed arrays.',
        ],
        'limitations': [
            'This auditor reads private oracle and both arms; it does not satisfy the separately required blind single-arm public consumer.',
            'Native terminal probe raw evidence is a boolean plus an executed assert comparing fresh native state with after state in archived test. A separate terminal native snapshot is not serialized.',
            'Existing scripted negative-control evidence checked here; separate root public consumer owns independent adversarial decoding.',
            'No external-model run, token cost, or model success/turn reduction has been established.',
            'No fresh Blender/GPU/performance samples run by this evidence auditor.',
        ],
        'required_rework': [] if complete else [
            'Keep formal_002 evidence and REWORK result. Re-run three independent processes, 5 warmups and 31 paired batches each, encoding all 22 publications of the same 20 tasks.',
            'Inside each timer construct the before package from original first-observation facts and encode it plus final for 19/20; do not prepend cached bytes.',
            'Record 22 actual publication sizes and 20 task sums per sample. Original 20-task median-byte and pooled p95 gates remain unchanged; schema and identical PNG remain separate.',
        ],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; preserve prior audits and use a new path.')
    report = audit(args.run.resolve(), args.previous.resolve() if args.previous else None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('decision', 'checks', 'measured_timing', 'gates_within_audit_scope')}, indent=2))
    return int(bool(report['checks']['errors']))


if __name__ == '__main__':
    sys.exit(main())
