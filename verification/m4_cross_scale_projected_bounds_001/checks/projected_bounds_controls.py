"""Qualify exact whole-scene projected bounds against installed and sealed inputs."""

import argparse
from collections import Counter
from dataclasses import asdict
from fractions import Fraction
import fractions
import gc
from hashlib import file_digest, sha256
from itertools import product
import json
from pathlib import Path
import random
from statistics import median
import subprocess
import sys
import time
import tracemalloc
from types import ModuleType
from unittest.mock import patch
from zipfile import ZipFile


HISTORY = '58920560404544bfc973463761bcd2db55acc5ff'
BASE_COMMIT = '3aa1d1fb43ae9a8207acd17bdab8d2861720c5a6'
BASE_SOURCE = 'b06f5e85a5d7b2519a09df2d7e5aa92ec2c915e860e58979837545c2851ded0a'
ASSEMBLY_ASSET = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
CROSS_SCALE_ASSET = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
NS = Path(__file__).resolve().parents[1]
REPO = NS.parents[1]
CAPTURES = (
    ('assembly_current', 'm4_cross_scale_pixel_evidence_001', 'P1', ASSEMBLY_ASSET,
     'a550a7018e07fc8e18204ffe77231b254d93a9558b2114036d2113898120a52b', (28, 416, 744, 188), True),
    ('assembly_historical', 'm4_assembly_evidence_consumption_001', 'A1', ASSEMBLY_ASSET,
     '81c84f4d7273cd9045702c7afb95b9c8fc21b02764106ff9d8289c7120e0964c', (28, 416, 744, 188), False),
    ('cross_scale', 'm4_cross_scale_cold_frustum_001', 'B1', CROSS_SCALE_ASSET,
     '31e69a857baf1f66e33722dec5ef63086565c0fbf3029c39071415782c7a0233', (21, 148, 184, 84), True),
)
MODULE = 'human_eye_plugin/active_observation.py'
PAIR_ORDER = ('A', 'B', 'B', 'A', 'A', 'B')


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def digest(value):
    return sha256(json.dumps(value, default=str, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class Pins:
    def __init__(self):
        self.rows = {}

    def add(self, label, size, checksum, expected=None):
        row = {'path': label, 'bytes': size, 'sha256': checksum}
        require(expected is None or checksum == expected, 'changed_frozen_input/' + label)
        require(self.rows.setdefault(label, row) == row, 'input_changed_in_process/' + label)

    def read(self, path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        self.add(str(path), len(raw), sha256(raw).hexdigest(), expected)
        return raw

    def file(self, path, expected=None):
        path = Path(path).resolve()
        with path.open('rb') as stream:
            checksum = file_digest(stream, 'sha256').hexdigest()
        self.add(str(path), path.stat().st_size, checksum, expected)

    def git(self, name):
        reference = f'{HISTORY}:verification/{name}'
        raw = subprocess.check_output(['git', 'show', reference], cwd=REPO)
        self.add(reference, len(raw), sha256(raw).hexdigest())
        return raw


def read_capture(pins, name, batch, slot, asset, frozen_terminal, size, has_cameras):
    run = Path('D:/he_' + batch)
    namespace = slot + '/'
    archive_index = json.loads(pins.git(batch + '/RUNTIME_INDEX.json'))
    members = {row['path']: row for row in archive_index['files']}
    require(len(members) == len(archive_index['files']), 'duplicate_archive_member/' + name)
    archive_path = Path(archive_index['archive']['path']).resolve()
    require(archive_path == (run / 'ORIGINAL_RUNTIME.zip').resolve(), 'invalid_original_archive/' + name)
    pins.file(archive_path, archive_index['archive']['sha256'])
    with ZipFile(archive_path) as archive:
        def original(leaf, expected=None):
            logical = 'slots/' + namespace + leaf
            member = members[logical]
            require(expected is None or expected == member['sha256'], 'wrong_bound_input/' + leaf)
            raw = pins.read(run / logical, member['sha256'])
            require(len(raw) == member['bytes'] and archive.read(logical) == raw,
                    'original_differs_from_archive/' + logical)
            return raw

        terminal = json.loads(original('TERMINAL_SOURCE.json', frozen_terminal))
        result = json.loads(original('SLOT_RESULT.json'))
        published = json.loads(original('SLOT_PUBLICATION.json'))
        config = json.loads(original('native/CONFIG.json'))
        original('native/input.blend', asset)
        producer = json.loads(original('product_full/call_001/SERVICE_RESULT.json')) if has_cameras else None
    source, receipt = terminal['source'], result['terminal_source']
    require(published['status'] == result['status'] and
            published['result_sha256'] == members['slots/' + namespace + 'SLOT_RESULT.json']['sha256']
            and receipt['status'] == 'complete' and receipt['terminal'] is True
            and receipt['sha256'] == receipt['worker']['sha256'] == frozen_terminal
            and source['pid'] == receipt['worker']['pid']
            and source['kind'] == 'actual_owned_Blender_evaluated_mesh'
            and source['asset_sha256'] == config['asset_sha256'] == asset
            and Path(source['asset_copy']).resolve() == (run / 'slots' / slot / 'native/input.blend').resolve()
            and source['frame'] == 1 and source['subframe'] == 0 and source['scale_length'] == 1.0
            and all(terminal['display_object_mask']), 'wrong_terminal_binding/' + name)
    meshes = terminal['objects']
    object_names = {mesh['name'] for mesh in meshes}
    scene = {'objects': [{'name': mesh['name'], 'vertices': mesh['evaluated']['vertices_world_m'],
                          'triangles': mesh['evaluated']['triangles']} for mesh in meshes]}
    sizes = (len(meshes), sum(len(mesh['vertices']) for mesh in scene['objects']),
             sum(len(mesh['triangles']) for mesh in scene['objects']))
    require(sizes == size[:3] and len(object_names) == sizes[0], 'scene_denominator_changed/' + name)
    evidence = {'terminal_sha256': frozen_terminal, 'asset_sha256': asset,
                'original_slot_status': result['status'], 'terminal_status': receipt['status'],
                'counts': dict(zip(('objects', 'vertices', 'triangles', 'regions'), size))}
    return scene, evidence, producer


def load_installed(pins, baseline_path, candidate_path):
    bindings = {tag: json.loads(pins.read(path))
                for tag, path in zip(('A', 'B'), (baseline_path, candidate_path))}
    a, b = bindings.values()
    require(a['preparation_git'] == BASE_COMMIT and a['source_sha256'] == BASE_SOURCE,
            'wrong_A_installed_identity')
    require(a['dependency_root'] == b['dependency_root'] and a['source_sha256'] != b['source_sha256'],
            'invalid_AB_identity')
    manifests = {tag: {row['path']: row['sha256'] for row in binding['source_manifest']}
                 for tag, binding in bindings.items()}
    old, new = manifests.values()
    require(len(old) == len(new) == 143 and old.keys() == new.keys() and
            [key for key in old if old[key] != new[key]] == [MODULE], 'unexpected_installed_source_difference')

    sys.path[:0] = [a['install_root'], a['dependency_root']]
    from human_eye_plugin.active_observation_host import freeze_cameras
    from human_eye_plugin.active_observation_images import _meshes_from_objects

    tools = {}
    for tag, binding in bindings.items():
        root = Path(binding['install_root']).resolve()
        for path in (MODULE, 'human_eye_plugin/active_observation_host.py',
                     'human_eye_plugin/active_observation_images.py',
                     'human_eye_plugin/active_observation_region_task.py'):
            original = pins.read(root / path, manifests[tag][path])
            if path == MODULE:
                module = ModuleType('_projected_bounds_installed_' + tag)
                module.__file__ = str(root / path)
                sys.modules[module.__name__] = module
                exec(compile(original, module.__file__, 'exec'), vars(module))
                tools[tag] = module
    return bindings, tools, freeze_cameras, _meshes_from_objects


def direct_test(api):
    q = Fraction
    eps = q(1, 2**100)
    center = q(10**20, 3)
    boxes = (
        ((0, 1), (0, 1)), ((0, 1), (0, 1)), ((0, 1), (-1, 1)),
        ((1, 2), (0, 1)), ((-2, -1), (1, 2)), ((0, 0), (0, 1)),
        ((-1, 1), (1, 1)), ((center, center + eps), (center, center + eps)),
        ((center + eps, center + 2*eps), (center - eps, center + 3*eps)),
    )
    named = {
        'touches_right_edge': ((1, q(3, 2)), (q(1, 2), 1)),
        'touches_left_edge': ((-1, 0), (0, 1)),
        'touches_top_edge': ((0, 1), (1, 2)),
        'touches_bottom_edge': ((0, 1), (-2, -1)),
        'touches_corner': ((2, 3), (1, 2)),
        'zero_region_x': ((1, 1), (0, 1)),
        'zero_region_y': ((0, 1), (1, 1)),
        'zero_triangle_x_and_y': ((-3, 3), (-3, 3)),
        'region_outside_all_endpoints': ((center + 1, center + 2), (center + 1, center + 2)),
        'region_below_all_endpoints': ((-100, -99), (-99, -98)),
        'non_triangle_endpoints_and_duplicates': ((q(1, 3), q(2, 3)), (q(1, 3), q(2, 3))),
        'exact_near_endpoint': ((center, center+eps), (center, center+eps)),
        'between_near_endpoints': ((center+eps/3, center+eps/2), (center+eps/3, center+eps/2)),
        'one_axis_disjoint': ((0, 1), (20, 21)),
    }
    randomizer = random.Random(441029)
    values = [q(i, 7) for i in range(-8, 9)] + [center + i*eps for i in range(-12, 13)]

    def random_box():
        return tuple(tuple(sorted(randomizer.choices(values, k=2))) for _ in range(2))

    boxes += tuple(random_box() for _ in range(256))
    x_ends, y_ends, ranks = api._rank_projected_boxes(boxes)
    require(len(ranks) == len(boxes), 'ranked_box_order_or_duplicates_lost')

    def matches(box):
        query = api._rank_region_bounds(box, x_ends, y_ends)
        expected = []
        for i, (a, b) in enumerate(boxes):
            p, q = box
            overlap_x = max(0, min(a[1], p[1]) - max(a[0], p[0]))
            overlap_y = max(0, min(b[1], q[1]) - max(b[0], q[0]))
            if overlap_x * overlap_y > 0:
                expected.append(i)
        actual = []
        if query is not None:
            lo_x, hi_x, lo_y, hi_y = query
            actual = [i for i, row in enumerate(ranks) if row is not None and
                      row[0] < hi_x and row[1] >= lo_x and row[2] < hi_y and row[3] >= lo_y]
        require(actual == expected, 'strict_rational_interval_mismatch/' + repr(box))
        return actual

    checks = {case: matches(box) for case, box in named.items()}
    randomized = [matches(random_box()) for _ in range(256)]
    require(not any(api._rank_projected_boxes(())), 'empty_rank_table_not_empty')
    return {'deterministic_regions': checks, 'generated_regions': len(randomized),
            'boxes_per_query': len(boxes), 'exact_predicate_comparisons': len(boxes)*(len(checks)+len(randomized)),
            'generated_matches_sha256': digest(randomized)}


def observed(api, args, scope, certify):
    real_plane, real_shadow, real_overlap = api.camera_planes, api.triangle_shadow, api.bounds_overlap
    real_rank = getattr(api, '_rank_projected_boxes', None)
    real_query = getattr(api, '_rank_region_bounds', None)
    observations, calls = {}, []
    count = None
    views = iter(args[-1]['views'])

    def camera_planes(camera):
        nonlocal count
        require(camera == next(views), 'view_order_changed')
        count = observations[camera['name']] = Counter()
        return real_plane(camera)

    def shadow(triangle, region, basis, planes, cached_screen=None):
        count['exact_depth_branches'] += 1
        calls.append((region.roi_id, triangle.object_index, triangle.triangle_index, triangle.key,
                      tuple(planes), cached_screen))
        require(triangle.object_index != region.object_index or
                triangle.triangle_index not in region.triangle_indices, 'own_source_reached_exact_depth_branch')
        return real_shadow(triangle, region, basis, planes, cached_screen)

    def overlap(first, second):
        result = real_overlap(first, second)
        count['legacy_overlap_comparisons'] += 1
        count['legacy_overlap_rejections'] += not result
        return result

    def rank(boxes):
        started = time.perf_counter_ns()
        ranked = real_rank(boxes)
        count['rank_prepare_ns'] += time.perf_counter_ns()-started
        count['rank_preparations'] += 1
        count['ranked_boxes'] = sum(row is not None for row in ranked[2])
        count['ordered_rank_rows'] = len(ranked[2])
        count['rank_x_endpoints'], count['rank_y_endpoints'] = map(len, ranked[:2])
        return ranked

    def query(*args):
        count['rank_region_lookups'] += 1
        return real_query(*args)

    mocks = {'camera_planes': camera_planes, 'triangle_shadow': shadow, 'bounds_overlap': overlap}
    if real_rank:
        mocks.update(_rank_projected_boxes=rank, _rank_region_bounds=query)
    work = {}
    with patch.multiple(api, **mocks):
        index = api.build_index_from_parsed(*args, patch_scope=scope,
                                          prove_frustum_containment=certify, frustum_work=work)
    return asdict(index), calls, {'views': observations, 'frustum_work': work}


def arguments(api, scene, cameras, *, regions_from=None):
    objects, triangles, identity = api.geometry(scene)
    regions, scope = api.partition_regions(objects, target_object_index=regions_from)
    return (objects, triangles, identity, regions, cameras), scope


def compare(apis, args_by_tag, *, certify, expected_rank_views):
    first, first_trace, a = observed(apis['A'], *args_by_tag['A'], certify)
    second, second_trace, b = observed(apis['B'], *args_by_tag['B'], certify)
    require(first == second, 'whole_coverage_index_changed')
    require(first_trace == second_trace, 'exact_depth_branch_sequence_changed')
    require({name for name, row in b['views'].items() if row['rank_preparations']} == expected_rank_views and
            sum(row['rank_preparations'] for row in b['views'].values()) == len(expected_rank_views),
            'wrong_ranked_view_eligibility')
    for name in b['views']:
        if name in expected_rank_views:
            require(not b['views'][name]['legacy_overlap_comparisons'], 'ranked_view_used_legacy_screen_test')
        else:
            for key in ('legacy_overlap_comparisons', 'legacy_overlap_rejections', 'exact_depth_branches'):
                require(a['views'][name][key] == b['views'][name][key], 'legacy_fallback_branch_count_changed')
    for key in ('frustum_certified_views', 'frustum_fallback_views', 'frustum_shadow_bypassed', 'frustum_shadow_legacy'):
        require(a['frustum_work'][key] == b['frustum_work'][key], 'frustum_count_changed/' + key)
    return first, first_trace, {'coverage_sha256': digest(first), 'exact_depth_trace_sha256': digest(first_trace),
                                'exact_depth_branches': len(first_trace), 'work': {'A': a, 'B': b}}


def independent_frustum_minimum(triangles, cameras):
    if not triangles:
        return {}
    points = {p for triangle in triangles for p in triangle.vertices}
    corner_bounds = tuple((min(p[i] for p in points), max(p[i] for p in points)) for i in range(3))
    minima = {}
    for camera in cameras['views']:
        view, projection = [tuple(tuple(Fraction(value) for value in row) for row in camera[key])
                            for key in ('view_matrix', 'projection_matrix')]
        corners = [(*point, Fraction(1)) for point in product(*corner_bounds)]
        transformed = (tuple(sum(c*v for c, v in zip(row, p)) for row in view) for p in corners)
        coordinate = (sum(c*v for c, v in zip(row, p)) for p in transformed for row in projection[:3])
        minima[camera['name']] = min(1-abs(c) for c in coordinate)
    return minima


def synthetic_cases(apis):
    q = Fraction(1, 4)
    h = Fraction(1, 2)
    eps = Fraction(1, 2**80)
    matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    cameras = {'views': [{'name': 'SCENE', 'direction_rational': [0, 0, 1], 'view_matrix': matrix,
                          'projection_matrix': matrix, 'size_px': [512, 512]}]}
    receiver = {'name': 'receiver', 'vertices': ((-h,-h,0), (h,-h,0), (h,h,0), (-h,h,0)),
                'triangles': ((0, 1, 2), (0, 2, 3))}
    equal_boxes = ((-q,-q,h), (q,q,h), (-q,q,h))
    earlier_distinct = ((-q,-q,h), (q,-q,h), (q,q,h))
    mere_touch = ((h,-q,h), (3*q,-q,h), (h,q,h))
    zero_x = ((0,-q,h), (0,0,3*q), (0,q,h))
    zero_y = ((-q,0,h), (q,0,3*q), (0,0,h))
    hidden_on_back = ((-q,-q,-h), (q,-q,-h), (0,q,-h))
    records = (
        ('touch_zero_and_behind', (mere_touch, zero_x, zero_y, hidden_on_back), True, (4,), None),
        ('duplicate_geometry_and_first_blocker', (equal_boxes, equal_boxes, earlier_distinct), True, (3,), 3),
        ('duplicate_geometry_uses_original_tie_order', (equal_boxes, equal_boxes), True, (1,), 1),
        ('uncertified_frustum_clips_crossing_triangle', (((-q,-q,h), (1+eps,-q,h), (0,q,h)),), True, (1,), 1),
        ('ordinary_path_stays_unranked_in_certifiable_view', (equal_boxes,), False, (1,), 1),
        ('near_but_separated_in_projection', (((h+eps,-q,h), (3*q,-q,h), (h+eps,q,h)),), True, (), None),
        ('strict_positive_overlap_below_binary64_resolution',
         (((h-eps,-q,h), (3*q,-q,h), (h-eps,q,h)),), True, (1,), 1),
    )
    results = {}
    for case, extras, certify, expected_trace, winner in records:
        scene = {'objects': [receiver] + [{'name': f'extra_{i}', 'vertices': vertices, 'triangles': ((0, 1, 2),)}
                                          for i, vertices in enumerate(extras)]}
        args_by_tag = {tag: arguments(api, scene, cameras, regions_from=0) for tag, api in apis.items()}
        args, _ = args_by_tag['A']
        minimum = independent_frustum_minimum(args[1], cameras)['SCENE']
        expected_ranked = certify and case != 'uncertified_frustum_clips_crossing_triangle'
        require(expected_ranked == (certify and minimum >= 0), 'synthetic_frustum_fixture_invalid/' + case)
        index, trace, result = compare(apis, args_by_tag, certify=certify,
                                       expected_rank_views={'SCENE'} if expected_ranked else set())
        row, = index['classifications']['SCENE'].values()
        require(tuple(call[1] for call in trace) == expected_trace, 'unexpected_synthetic_depth_trace/' + case)
        require(row['status'] == ('complete' if winner is None else 'positive_area_occlusion'),
                'unexpected_synthetic_occlusion/' + case)
        if winner is not None:
            triangle, = [tri for tri in args[1] if tri.object_index == winner]
            require(row['first_blocker']['triangle_geometry_id'] == apis['A'].fingerprint(triangle.key),
                    'first_blocker_order_changed/' + case)
        results[case] = result | {'independent_frustum_minimum': str(minimum), 'expected_trace_objects': expected_trace,
                                  'classification': row}
    return results


def profile_peak(fn):
    gc.collect()
    tracemalloc.start()
    try:
        result = fn()
        retained, peak = tracemalloc.get_traced_memory()
        del result
        after_release, _ = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {'peak_bytes': peak, 'retained_with_result_bytes': retained, 'after_result_release_bytes': after_release}


def larger_rank_tables(api):
    rows = []
    hash_cache = getattr(fractions, '_hash_algorithm', None)
    for n in (2048, 4096, 8192):
        boxes = tuple(((Fraction(3*i, 13), Fraction(3*i+1, 13)),
                      (Fraction(3*i+1, 11), Fraction(3*i+2, 11))) for i in range(n))
        counts = tuple(map(len, api._rank_projected_boxes(boxes)))
        require(counts == (2*n, 2*n, n), 'nonlinear_endpoint_or_box_denominator')
        started = time.perf_counter_ns()
        api._rank_projected_boxes(boxes)
        elapsed = time.perf_counter_ns()-started
        warm = profile_peak(lambda: api._rank_projected_boxes(boxes))
        cache = None
        if hash_cache is not None and hasattr(hash_cache, 'cache_clear'):
            hash_cache.cache_clear()
            cold = profile_peak(lambda: api._rank_projected_boxes(boxes))
            cache = dict(hash_cache.cache_info()._asdict())
        else:
            cold = warm
        rows.append({'boxes': n, 'endpoint_and_rank_row_counts': counts,
                     'preparation_ns': elapsed, 'warm_peak': warm, 'cleared_hash_cache_peak': cold,
                     'hash_cache_after_cold_trace': cache})
    ratios = {condition: [big[condition]['peak_bytes']/small[condition]['peak_bytes']
                         for small,big in zip(rows,rows[1:])]
              for condition in ('warm_peak', 'cleared_hash_cache_peak')}
    return {'samples': rows, 'peak_doubling_ratios': ratios, 'memory_method': 'tracemalloc, input excluded',
            'structural_bounds': {'working_intermediate_rows_limit_per_box': 1, 'retained_output_rows_per_box': 1,
                                  'unique_endpoints_limit_per_box_per_axis': 2,
                                  'rank_map_entries_limit_per_box_per_axis': 2,
                                  'scope': 'Current-view rank containers only, excluding the scene and preexisting caches.'},
            'runtime_hash_cache': 'CPython Fraction hash LRU may retain bounded allocations after the result is deleted.'}


def performance(apis, args_by_tag, measure_memory):
    samples = {'A': [], 'B': []}
    for ordinal, tag in enumerate(PAIR_ORDER):
        args, scope = args_by_tag[tag]
        started = time.perf_counter_ns()
        cpu_started = time.process_time_ns()
        index = apis[tag].build_index_from_parsed(*args, patch_scope=scope, prove_frustum_containment=True,
                                                frustum_work={})
        samples[tag].append({'wall_ns': time.perf_counter_ns()-started,
                             'cpu_ns': time.process_time_ns()-cpu_started, 'sequence_ordinal': ordinal+1})
        del index
    drops = [1-new['wall_ns']/old['wall_ns'] for old,new in zip(samples['A'], samples['B'])]
    peaks = {}
    if measure_memory:
        for tag, api in apis.items():
            args, scope = args_by_tag[tag]
            peaks[tag] = profile_peak(lambda: api.build_index_from_parsed(
                *args, patch_scope=scope, prove_frustum_containment=True, frustum_work={}))
    return {'samples': samples, 'pair_order': PAIR_ORDER, 'pair_fractional_wall_reduction': drops,
            'median_paired_wall_reduction': median(drops),
            'median_wall_ns': {tag: median(row['wall_ns'] for row in values) for tag, values in samples.items()},
            'python_traced_full_index_memory': peaks}


def exercise_scene(apis, freeze, mesh_adapter, name, scene, evidence, producer):
    objects, _, _ = apis['A'].geometry(scene)
    cameras = freeze(mesh_adapter(objects))
    args_by_tag = {tag: arguments(api, scene, cameras) for tag, api in apis.items()}
    args, _ = args_by_tag['A']
    minima = independent_frustum_minimum(args[1], cameras)
    require(len(args[3]) == evidence['counts']['regions'] and len(minima) == 6 and min(minima.values()) >= 0,
            'expected_full_certificate_or_region_count_missing/' + name)
    _, _, coverage = compare(apis, args_by_tag, certify=True, expected_rank_views=set(minima))
    locals_ = {}
    if producer is not None:
        require(producer['binding']['camera_specification'] == cameras, 'camera_differs_from_actual/' + name)
        for local in producer['scopes']:
            if local['scope_id'] == 'global':
                continue
            local_camera = local['binding']['camera_specification']
            roi, = local['facts']['regions']
            local_args = {}
            for tag, (prepared, _) in args_by_tag.items():
                region, = [candidate for candidate in prepared[3] if candidate.roi_id == roi['roi_id']]
                local_args[tag] = ((*prepared[:3], (region,), local_camera), ())
            _, trace, result = compare(apis, local_args, certify=False, expected_rank_views=set())
            require(trace and result['work']['B']['frustum_work']['frustum_shadow_legacy'] == len(trace),
                    'actual_local_legacy_not_exercised')
            local_minima = independent_frustum_minimum(args[1], local_camera)
            locals_[roi['object_name']] = result | {'independent_frustum_minima': {
                view: str(minimum) for view, minimum in local_minima.items()}}
    require(set(locals_) == {'assembly_current': {'N10'}, 'cross_scale': {'M02', 'M09'},
                             'assembly_historical': set()}[name], 'sealed_local_camera_missing/' + name)
    return evidence | coverage | {'independent_frustum_minima': {key: str(value) for key,value in minima.items()},
                                  'exact_camera_sha256': digest(cameras), 'local_fallback': locals_,
                                  'direct_coverage': performance(apis, args_by_tag, name != 'assembly_historical')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    pins = Pins()
    pins.read(__file__)
    pins.file(sys.executable)
    pins.read(NS / 'checks/FIRST_OFFLINE_FAILURE.txt')
    bindings, apis, freeze, mesh_adapter = load_installed(pins, args.baseline, args.candidate)
    endpoints = direct_test(apis['B'])
    synthetic = synthetic_cases(apis)
    scenes = {}
    for capture in CAPTURES:
        name = capture[0]
        scene, evidence, producer = read_capture(pins, *capture)
        print('Checking exact and timed offline coverage for ' + name, file=sys.stderr, flush=True)
        scenes[name] = exercise_scene(apis, freeze, mesh_adapter, name, scene, evidence, producer)
    assembly = scenes['assembly_current']['direct_coverage']
    space = larger_rank_tables(apis['B'])
    passed = assembly['median_paired_wall_reduction'] > 0
    result = {
        'kind': 'm4-cross-scale-projected-bounds-controls-v1', 'passed': passed,
        'offline_gates': {'full_exact_index_and_order': True, 'edge_and_fallback_controls': True,
                          'linear_temporary_growth': True, 'assembly_median_paired_wall_reduction_positive': passed},
        'owned_Blender': 0, 'model_consumers': 0, 'actual_new_rasters': 0,
        'product_identity': {tag: {key: binding[key] for key in
                             ('install_root', 'preparation_git', 'source_sha256')} for tag, binding in bindings.items()},
        'sources': list(pins.rows.values()), 'scenes': scenes, 'strict_axis_predicates': endpoints,
        'synthetic_scene_controls': synthetic, 'rank_memory_growth': space,
    }
    with args.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': passed, 'output': str(args.output),
                      'median_paired_reductions': {name: row['direct_coverage']['median_paired_wall_reduction']
                                                   for name, row in scenes.items()}}))
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
