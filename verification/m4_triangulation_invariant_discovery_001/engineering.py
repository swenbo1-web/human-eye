"""Finite triangulation qualification, five index pairs and fresh observation chains."""

import argparse
from fractions import Fraction
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
import traceback


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / 'verification/m4_active_coverage_001'
SITE = Path('D:/hefe/.human-eye/releases/9.7.2+20261028.support.discovery.r1/.venv/Lib/site-packages')
SCENES = {
    'original': 'scene_original.json',
    'grid4_uniform': 'scene_grid4_uniform.json',
    'grid4_permuted_alternating': 'scene_grid4_permuted_alternating.json',
    'grid16_uniform': 'scene_grid16_uniform.json',
    'grid16_permuted_alternating': 'scene_grid16_permuted_alternating.json',
}
PAIR_ORDER = (('reference', 'candidate'), ('candidate', 'reference'), ('reference', 'candidate'),
              ('candidate', 'reference'), ('reference', 'candidate'))
_RUNTIME = None


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, allow_nan=False, indent=2) + '\n').encode('utf8')


def save(path, value):
    raw = encoded(value)
    with Path(path).open('wb') as stream:
        stream.write(raw)
    return {'bytes': len(raw), 'sha256': digest(raw)}


def new_output(path):
    path = Path(path).resolve()
    if not path.is_relative_to(HERE):
        raise ValueError('new_namespace_output_required')
    path.mkdir(parents=True, exist_ok=False)
    return path


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def runtime():
    global _RUNTIME
    if _RUNTIME is None:
        began = time.perf_counter_ns()
        sys.path.insert(0, str(SITE))
        discovery = load_module('_triangulation_new_discovery', HERE / 'discovery.py')
        core = discovery.legacy
        adapter = load_module('_triangulation_fixed_raster', OLD / 'render/adapter.py')
        dependencies = adapter.dependency_binding()
        _RUNTIME = {'core': core, 'adapter': adapter, 'discovery': discovery,
                    'setup': {'started_ns': began, 'closed_ns': time.perf_counter_ns(),
                              'dependencies': dependencies, 'discovery_source_binding': discovery.source_binding(),
                              'scope': 'One shared module/import and fixed-source binding, outside benchmark trials.'}}
    return _RUNTIME


def interval(started, closed):
    return {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}


def region_row(region):
    return {'roi_id': region.roi_id, 'object_index': region.object_index, 'object_name': region.object_name,
            'triangle_indices': list(region.triangle_indices),
            'vertices': [[str(value) for value in point] for point in region.vertices],
            'normal': [str(value) for value in region.normal]}


def expected_region(row):
    return {'roi_id': row['roi_id'], 'object_index': row['object_index'], 'object_name': row['object_name'],
            'triangle_indices': list(row['triangle_indices']),
            'vertices': [[str(Fraction(value)) for value in point] for point in row['vertices']],
            'normal': [str(Fraction(value)) for value in row['normal']]}


def index_row(index):
    return {'scene_identity': index.scene_identity, 'candidate_identity': index.candidate_identity,
            'regions': [region_row(value) for value in index.regions], 'view_order': list(index.view_order),
            'view_masks': index.view_masks, 'classifications': index.classifications, 'stats': index.stats}


def build_trial(scene_path, variant):
    modules = runtime()
    discovery = modules['discovery']
    stages = {}
    began = time.perf_counter_ns()
    raw = Path(scene_path).read_bytes()
    camera_raw = (HERE / 'inputs/CAMERAS.json').read_bytes()
    scene_sha, camera_sha = digest(raw), digest(camera_raw)
    scene, cameras = json.loads(raw), json.loads(camera_raw)
    closed = time.perf_counter_ns()
    stages['read_hash_JSON'] = interval(began, closed)
    stats = {}
    mark = closed
    objects, triangles, identity = discovery.parse_geometry(scene, stats=stats)
    closed = time.perf_counter_ns()
    stages['Fraction_geometry_and_scene_identity'] = interval(mark, closed)
    mark = closed
    regions = discovery.regions_from_objects(objects, discovery_variant=variant, stats=stats)
    closed = time.perf_counter_ns()
    stages['discovery'] = interval(mark, closed)
    mark = closed
    index = discovery.build_index_from_parsed(objects, triangles, identity, regions, cameras)
    closed = time.perf_counter_ns()
    stages['old_optimized_index'] = interval(mark, closed)
    # Diagnostics follow the authoritative index-return timestamp.
    values = [value for obj in objects for point in obj[0] for value in point]
    numeric = {'source_coordinate_Fractions': len(values),
               'maximum_coordinate_numerator_bits': max((abs(value.numerator).bit_length() for value in values), default=0),
               'maximum_coordinate_denominator_bits': max((value.denominator.bit_length() for value in values), default=0),
               'scope': 'Input coordinates only. Derived intermediate bit lengths are limited to discovery-provided diagnostics.'}
    record = {'variant': variant, **interval(began, closed), 'stages': stages,
              'scene_path': str(Path(scene_path).resolve()), 'scene_sha256': scene_sha, 'camera_sha256': camera_sha,
              'scene_JSON_bytes': len(raw), 'camera_JSON_bytes': len(camera_raw),
              'discovery_stats': stats, 'coordinate_diagnostics': numeric,
              'RSS_bytes': None, 'Python_geometry_resident_bytes': None,
              'scope': 'Before input read/hash/JSON through Fraction geometry/hash, discovery and fixed optimized index return. Post-return verification/serialization and shared setup are separate.'}
    return scene, cameras, index, record


def area_work(stats):
    work = stats['discovery']['work']
    return {key: work[key] for key in ('area_rational_multiply_calls',
                                      'area_rational_subtract_calls', 'area_rational_add_calls')}


def truth_for_scene(proof, key):
    if key in proof['scenes']:
        return proof['scenes'][key]
    name = SCENES[key]
    return next(value for value in proof['scenes'].values() if Path(value['path']).name == name)


def qualify_index(scene, index, expected, proof):
    actual = [region_row(value) for value in index.regions]
    wanted = [expected_region(value) for value in expected['expected_regions']]
    assert sorted(actual, key=lambda value: value['roi_id']) == sorted(wanted, key=lambda value: value['roi_id'])
    for region in index.regions:
        assert list(region.triangle_indices) == list(range(len(scene['objects'][region.object_index]['triangles'])))
    assert index.view_masks == proof['view_masks']
    compared = 0
    for name, rows in proof['geometry_by_view'].items():
        for identity, expected_row in rows.items():
            current = index.classifications[name][identity]
            assert current['status'] == expected_row['status'] and current['complete'] is expected_row['complete']
            compared += 1
    assert compared == 36
    return {'passed': True, 'regions': len(actual), 'source_triangle_indices_verified': True,
            'independent_geometry_rows_verified': compared}


def legacy_baseline(output):
    output = new_output(output)
    modules = runtime()
    rows = []
    for key, name in SCENES.items():
        began = time.perf_counter_ns()
        path = HERE / 'inputs' / name
        scene = json.loads(path.read_bytes())
        regions = modules['core'].discover_regions(scene)
        rows.append({'scene': key, 'source_sha256': digest(path.read_bytes()),
                     **interval(began, time.perf_counter_ns()), 'regions': [region_row(value) for value in regions],
                     'discovered_count': len(regions)})
    value = {'rows': rows, 'shared_setup': modules['setup'],
             'scope': 'One old discovery call per fixed representation. Subdivision is outside the older four-vertex/two-face discovery domain.'}
    save(output / 'RESULTS.json', value)
    return value


def correctness(output):
    output = new_output(output)
    proof = json.loads((HERE / 'proof/EXPECTED.json').read_bytes())
    rows = []
    for key, name in SCENES.items():
        for variant in ('reference', 'candidate'):
            row = {'scene': key, 'variant': variant, 'passed': False}
            try:
                scene, _, index, trial = build_trial(HERE / 'inputs' / name, variant)
                row.update(trial=trial, index=index_row(index),
                           qualification=qualify_index(scene, index, truth_for_scene(proof, key), proof), passed=True)
            except BaseException as error:
                row['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
            rows.append(row)
            save(output / 'PROGRESS.json', rows)
    discovery = runtime()['discovery']
    for key in ('rotated_grid4', 'hole_grid4'):
        specification = proof['controls'][key]
        path = Path(specification['path'])
        if not path.is_absolute():
            path = HERE / path
        scene = json.loads(path.read_bytes())
        for variant in ('reference', 'candidate'):
            row = {'control': key, 'variant': variant, 'passed': False}
            try:
                objects, _, _ = discovery.parse_geometry(scene)
                regions = discovery.regions_from_objects(objects, discovery_variant=variant)
                actual = [region_row(value) for value in regions]
                wanted = [expected_region(value) for value in specification['expected_regions']]
                assert actual == wanted
                row.update(passed=True, regions=actual)
            except BaseException as error:
                row['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
            rows.append(row)
    value = {'passed': all(row['passed'] for row in rows), 'rows': rows,
             'proof_sha256': digest((HERE / 'proof/EXPECTED.json').read_bytes()), 'shared_setup': runtime()['setup'],
             'new_renders': 0, 'scope': 'Five representations times two discovery variants plus two discovery-only controls per variant.'}
    save(output / 'RESULTS.json', value)
    return value


def benchmark(output):
    output = new_output(output)
    with (HERE / 'BENCHMARK_STARTED.json').open('x', encoding='utf8') as marker:
        json.dump({'started_ns': time.perf_counter_ns(), 'output': str(output), 'pairs': PAIR_ORDER}, marker)
    modules = runtime()
    proof = json.loads((HERE / 'proof/EXPECTED.json').read_bytes())
    key = 'grid16_permuted_alternating'
    rows = []
    for pair, order in enumerate(PAIR_ORDER, 1):
        for variant in order:
            row = {'pair': pair, 'variant': variant, 'passed': False}
            try:
                scene, _, index, trial = build_trial(HERE / 'inputs' / SCENES[key], variant)
                row.update(trial)
                row['qualification'] = qualify_index(scene, index, truth_for_scene(proof, key), proof)
                row.update(index=index_row(index), passed=True)
            except BaseException as error:
                row['error'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
            rows.append(row)
            save(output / 'PROGRESS.json', rows)
    passed = all(row['passed'] for row in rows)
    pairs = []
    if passed:
        for pair in range(1, 6):
            ref = next(row for row in rows if row['pair'] == pair and row['variant'] == 'reference')
            candidate = next(row for row in rows if row['pair'] == pair and row['variant'] == 'candidate')
            pairs.append({'pair': pair, 'reference_ns': ref['elapsed_ns'], 'candidate_ns': candidate['elapsed_ns'],
                          'candidate_over_reference': candidate['elapsed_ns'] / ref['elapsed_ns']})
    reference_total = sum(row.get('elapsed_ns', 0) for row in rows if row['variant'] == 'reference') if passed else None
    candidate_total = sum(row.get('elapsed_ns', 0) for row in rows if row['variant'] == 'candidate') if passed else None
    work_totals = {variant: {key: sum(area_work(row['discovery_stats'])[key] for row in rows if row['variant'] == variant)
                             for key in ('area_rational_multiply_calls', 'area_rational_subtract_calls', 'area_rational_add_calls')}
                   for variant in ('reference', 'candidate')} if passed else None
    work_reduced = bool(passed and all(work_totals['candidate'][key] <= work_totals['reference'][key]
                                      for key in work_totals['reference'])
                        and any(work_totals['candidate'][key] < work_totals['reference'][key]
                                for key in work_totals['reference']))
    value = {'passed': passed, 'rows': rows, 'pairs': pairs, 'shared_setup': modules['setup'],
             'pair_ratio_median': statistics.median(row['candidate_over_reference'] for row in pairs) if pairs else None,
             'reference_total_ns': reference_total, 'candidate_total_ns': candidate_total,
             'recorded_area_Fraction_work': work_totals, 'area_Fraction_work_reduced': work_reduced,
             'timing_nonregression': bool(passed and statistics.median(row['candidate_over_reference'] for row in pairs) <= 1
                                          and candidate_total <= reference_total),
             'candidate_retention_pending': 'Also requires all new-pixel/correctness equivalence and documented actual Fraction-work reduction.',
             'new_renders': 0, 'RSS_bytes': None, 'scope': 'Exactly five paired complete fresh-input index trials. No timing resampling or statistical significance claim.'}
    save(output / 'RESULTS.json', value)
    return value


def reserve_render(budget, output, view, variant):
    budget = Path(budget).resolve()
    if not budget.is_relative_to(HERE):
        raise ValueError('new_namespace_global_budget_required')
    budget.mkdir(parents=True, exist_ok=True)
    for number in range(1, 17):
        path = budget / (str(number).zfill(2) + '.json')
        try:
            with path.open('x', encoding='utf8') as stream:
                value = {'attempt': number, 'view': view, 'variant': variant,
                         'output': str(output), 'started_ns': time.perf_counter_ns(), 'status': 'intent'}
                json.dump(value, stream)
                stream.flush()
                os.fsync(stream.fileno())
            return value
        except FileExistsError:
            continue
    raise RuntimeError('sixteen_total_render_attempts_exhausted')


def canonical_readability(adapter, meshes, pose, buffers, regions):
    np = adapter.np
    view, projection = np.asarray(pose['view_matrix']), np.asarray(pose['projection_matrix'])
    direction = np.asarray(pose['target_to_eye_unit'])
    rows = []
    for region in regions:
        mesh = meshes[region.object_index]
        corners = np.asarray([[float(value) for value in point] for point in region.vertices])
        camera = corners @ view[:3, :3].T + view[:3, 3]
        ndc = camera @ projection[:3, :3].T + projection[:3, 3]
        pixels = (ndc[:, :2] + 1) * (adapter.SIZE - 1) / 2
        front = bool(np.asarray([float(value) for value in region.normal]) @ direction > 0)
        evidence = adapter._readability_evidence(buffers['color'], buffers['owners'], meshes, (mesh.object_id,), pixels)
        rows.append({'roi_id': region.roi_id, 'object_index': region.object_index, 'view': pose['name'],
                     'front_facing': front, 'visible_surface_pixels': evidence['visible_surface_pixels'][0],
                     'contrasting_boundary_pixels': evidence['contrasting_boundary_pixels'][0],
                     'readable': front and evidence['passed'], 'triangle_indices': list(region.triangle_indices),
                     'source_vertices': len(mesh.vertices), 'source_triangles': len(mesh.faces),
                     'minimum_surface_pixels': 16, 'minimum_boundary_pixels': 4, 'minimum_rgb_boundary_contrast': 24})
    return rows


def independent_pixels(buffers, regions):
    """Count owners and contrast-adjacent endpoints using integer Python sets."""
    owners = buffers['owners'].tolist()
    color = buffers['color'].tolist()
    depth = buffers['depth'].tolist()
    height, width = buffers['owners'].shape
    assert tuple(buffers['depth'].shape) == (height, width)
    assert tuple(buffers['color'].shape) == (height, width, 3)
    foreground_pixels = background_pixels = 0
    targets = {region.object_index for region in regions}
    surface = {index: 0 for index in targets}
    boundary = {index: set() for index in targets}
    for y in range(height):
        for x in range(width):
            first = owners[y][x]
            value = depth[y][x]
            if first < 0:
                assert first == -1 and math.isinf(value) and value > 0, ('background_depth', y, x, value)
                background_pixels += 1
            else:
                assert math.isfinite(value) and value > 0, ('foreground_depth', y, x, value)
                foreground_pixels += 1
            if first in targets:
                surface[first] += 1
            for ny, nx in ((y + 1, x), (y, x + 1)):
                if ny >= height or nx >= width or first == owners[ny][nx]:
                    continue
                second = owners[ny][nx]
                if first not in targets and second not in targets:
                    continue
                squared = sum((a - b) ** 2 for a, b in zip(color[y][x], color[ny][nx]))
                if squared >= 24 * 24:
                    if first in targets:
                        boundary[first].add((y, x))
                    if second in targets:
                        boundary[second].add((ny, nx))
    return {'counts': {region.roi_id: {'visible_surface_pixels': surface[region.object_index],
                                      'contrasting_boundary_pixels': len(boundary[region.object_index])}
                       for region in regions},
            'depth_checks': {'depth_RGB_owner_shapes_match': True, 'background_depth_is_positive_infinity': True,
                             'foreground_depth_is_finite_positive': True, 'foreground_pixels': foreground_pixels,
                             'background_pixels': background_pixels, 'checked_pixels': height * width}}


def observe_chain(scene_key, variant, output, budget):
    began = time.perf_counter_ns()
    output = new_output(output)
    if scene_key not in ('grid4_permuted_alternating', 'grid16_permuted_alternating') or variant not in ('reference', 'candidate'):
        raise ValueError('registered_four_observation_chains_only')
    modules = runtime()
    core, adapter = modules['core'], modules['adapter']
    frames, steps, errors = {}, [], []
    index = state = None
    try:
        scene, cameras, index, trial = build_trial(HERE / 'inputs' / SCENES[scene_key], variant)
        state = core.CoverageState(index)
        meshes = adapter.load_meshes(scene)
        for mesh, source in zip(meshes, scene['objects']):
            assert mesh.faces.tolist() == source['triangles']
        poses = {pose['name']: pose for pose in cameras['views']}
        with (output / 'TRACE.jsonl').open('xb') as trace:
            while True:
                name = state.next_view()
                if name is None:
                    break
                if name in frames:
                    raise RuntimeError('state_selected_an_already_observed_view')
                intent = reserve_render(budget, output, name, variant)
                frame = {'view': name, 'attempt': intent, 'status': 'intent', 'stages': {}}
                frames[name] = frame
                trace.write(encoded({'event': 'render_attempt', **intent}))
                trace.flush()
                os.fsync(trace.fileno())
                folder = output / ('frame_' + str(len(frames)).zfill(2) + '_' + name)
                folder.mkdir()
                mark = time.perf_counter_ns()
                buffers = adapter.render_one(meshes, poses[name])
                frame['stages']['actual_raster'] = interval(mark, time.perf_counter_ns())
                frame['arrays'] = {key: {'dtype': str(value.dtype), 'shape': list(value.shape), 'nbytes': int(value.nbytes),
                                          'sha256': digest(value.tobytes(order='C'))} for key, value in buffers.items()}
                mark = time.perf_counter_ns()
                png, npz = folder / (name + '.png'), folder / (name + '.npz')
                with png.open('xb') as stream:
                    adapter.Image.fromarray(buffers['color'], mode='RGB').save(stream, format='PNG')
                with npz.open('xb') as stream:
                    adapter.np.savez_compressed(stream, **buffers)
                frame['stages']['PNG_NPZ_publication'] = interval(mark, time.perf_counter_ns())
                frame.update(PNG=str(png), PNG_bytes=png.stat().st_size, PNG_sha256=digest(png.read_bytes()),
                             NPZ=str(npz), NPZ_bytes=npz.stat().st_size, NPZ_sha256=digest(npz.read_bytes()))
                mark = time.perf_counter_ns()
                pixels = canonical_readability(adapter, meshes, poses[name], buffers, index.regions)
                frame['stages']['production_readability'] = interval(mark, time.perf_counter_ns())
                mark = time.perf_counter_ns()
                recount = independent_pixels(buffers, index.regions)
                recounted = recount['counts']
                frame['stages']['independent_pixel_recount'] = interval(mark, time.perf_counter_ns())
                for row in pixels:
                    assert row['visible_surface_pixels'] == recounted[row['roi_id']]['visible_surface_pixels']
                    assert row['contrasting_boundary_pixels'] == recounted[row['roi_id']]['contrasting_boundary_pixels']
                    assert row['readable'] is bool(row['front_facing'] and row['visible_surface_pixels'] >= 16 and row['contrasting_boundary_pixels'] >= 4)
                receipt = {'scene_identity': index.scene_identity, 'candidate_identity': index.candidate_identity,
                           'view_name': name, 'actual_image_delivered': True, 'image_path': str(png),
                           'image_sha256': frame['PNG_sha256'], 'pixel_evidence_scope': 'actual_common_depth_owner',
                           'readable_roi_ids': sorted(row['roi_id'] for row in pixels if row['readable']),
                           'scope': 'New local raster evidence delivered to this engineering observer. No model consumer.'}
                complete = set(index.ids(index.view_masks[name]))
                added = state.observe(receipt)
                step = {'view': name, 'geometrically_complete_roi_ids': sorted(complete),
                        'pixel_shortfall_roi_ids': sorted(complete - set(receipt['readable_roi_ids'])),
                        'receipt': receipt, 'update': added, 'next_view': state.next_view()}
                frame.update(status='completed', pixel_rows=pixels, independent_counts=recounted,
                             depth_checks=recount['depth_checks'])
                save(folder / 'FRAME.json', frame)
                steps.append(step)
                trace.write(encoded({'event': 'frame_complete', 'attempt': intent['attempt'], 'view': name,
                                     'PNG_sha256': frame['PNG_sha256']}))
                trace.flush()
                save(output / 'PROGRESS.json', {'frames': frames, 'steps': steps})
    except BaseException as error:
        errors.append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
        for frame in frames.values():
            if frame['status'] != 'completed':
                frame.update(status='failed', error=errors[-1])
    history = {identity for step in steps for identity in step['pixel_shortfall_roi_ids']}
    final_state = None if state is None else state.summary()
    value = {'scene': scene_key, 'variant': variant, 'passed': not errors, 'errors': errors,
             'index': None if index is None else index_row(index), 'frames': frames, 'steps': steps,
             'final_state': final_state,
             'final_pixel_shortfall_roi_ids': sorted(history.intersection(final_state['unresolved_roi_ids'])) if final_state else [],
             'actual_chain_render_attempts': len(frames), 'global_budget_directory': str(Path(budget).resolve()),
             'started_ns': began, 'before_result_publication_ns': time.perf_counter_ns(),
             'shared_setup': modules['setup'], 'RSS_bytes': None,
             'array_payload_bytes': sum(item['nbytes'] for frame in frames.values() for item in frame.get('arrays', {}).values()),
             'new_models_or_Blender': 0, 'scope': 'One fresh application-cache engineering chain, including independent pixel audit and file publication. Single-run timings are descriptive.'}
    save(output / 'RESULTS.json', value)
    closed = time.perf_counter_ns()
    save(output / 'FINAL_TIMING.json', interval(began, closed))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('legacy', 'correctness', 'benchmark', 'observe'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scene', choices=('grid4_permuted_alternating', 'grid16_permuted_alternating'))
    parser.add_argument('--variant', choices=('reference', 'candidate'))
    parser.add_argument('--budget', type=Path)
    options = parser.parse_args()
    if options.phase == 'observe':
        if options.scene is None or options.variant is None or options.budget is None:
            raise ValueError('registered_scene_variant_and_shared_budget_required')
        result = observe_chain(options.scene, options.variant, options.output, options.budget)
    else:
        result = {'legacy': legacy_baseline, 'correctness': correctness, 'benchmark': benchmark}[options.phase](options.output)
    print(json.dumps({'phase': options.phase, 'passed': result.get('passed'), 'new_model_calls': 0}))


if __name__ == '__main__':
    main()
