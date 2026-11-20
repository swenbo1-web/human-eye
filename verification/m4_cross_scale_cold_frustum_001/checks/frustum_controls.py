"""Compare installed frustum paths using exact geometry and two sealed Blender sources."""

import argparse
from collections import Counter
from dataclasses import asdict, replace
from fractions import Fraction
import hashlib
import inspect
from itertools import product
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch
from zipfile import ZipFile


NS = Path(__file__).resolve().parents[1]
V = NS.parent
FORMAL = V / 'm4_cross_scale_live_task_formal_001'
A = V / 'm4_cross_scale_global_index_reuse_001'
ASSEMBLY = V / 'm4_assembly_evidence_consumption_001'
PRIMARY_RUN = Path('D:/he_m4_cross_scale_global_index_reuse_001')
SECONDARY_RUN = Path('D:/he_m4_assembly_evidence_consumption_001')
SECONDARY_ASSET = '91129d2e82749162bd0c9f4b232be10bd74d422be53c73e248325c0894b14a85'
PRIMARY_ASSET = 'f5469ae84503fdad436f2d6dd86efaa6666f1af1fb80ef9b38af15cbc1ece8ce'
TRUTH_SHA = '376a31b5a5cfc0e979f6b43d43756d9837dbfae9c53b96c77f46cc329b2ba922'
TWO_RUNS = (('fixed', PRIMARY_RUN, A, PRIMARY_ASSET, (21, 148, 184, 84)),
            ('assembly_transfer', SECONDARY_RUN, ASSEMBLY, SECONDARY_ASSET, (28, 416, 744, 188)))


def require(condition, why):
    if not condition:
        raise ValueError(why)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def object_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode())


class Pins:
    def __init__(self):
        self.entries = {}

    def bytes(self, path, expected=None):
        path = Path(path).resolve()
        raw = path.read_bytes()
        row = {'path': str(path), 'sha256': digest(raw), 'bytes': len(raw)}
        require(expected is None or row['sha256'] == expected, 'changed_source/' + str(path))
        require(self.entries.setdefault(path, row) == row, 'input_changed_in_process/' + str(path))
        return raw

    def read(self, path, expected=None):
        return json.loads(self.bytes(path, expected))


def sealed_capture(pins, run, batch, asset_sha, size):
    runtime_index = pins.read(batch / 'RUNTIME_INDEX.json')
    paths = {row['path']: row for row in runtime_index['files']}
    require(len(paths) == len(runtime_index['files']), 'ambiguous_runtime_manifest')

    def bound(name, raw=False):
        logical = 'slots/A1/' + name
        row = paths[logical]
        content = pins.bytes(run / logical, row['sha256'])
        require(len(content) == row['bytes'], 'archive_original_size/' + logical)
        with ZipFile(archive_path) as archive:
            require(archive.read(logical) == content, 'archive_original_bytes/' + logical)
        return content if raw else json.loads(content)

    archive_info = runtime_index['archive']
    archive_path = Path(archive_info['path']).resolve()
    require(archive_path == (run / 'ORIGINAL_RUNTIME.zip').resolve(), 'wrong_runtime_archive')
    pins.bytes(archive_path, archive_info['sha256'])
    terminal = bound('TERMINAL_SOURCE.json')
    outcome = bound('SLOT_RESULT.json')
    publication = bound('SLOT_PUBLICATION.json')
    config = bound('native/CONFIG.json')
    copy = bound('native/input.blend', raw=True)
    receipt, source = outcome['terminal_source'], terminal['source']
    terminal_path = run / 'slots/A1/TERMINAL_SOURCE.json'
    published_sha = paths['slots/A1/SLOT_RESULT.json']['sha256']
    expected_sha = paths['slots/A1/TERMINAL_SOURCE.json']['sha256']
    native_copy = (run / 'slots/A1/native/input.blend').resolve()
    require(publication['result_sha256'] == published_sha and publication['slot'] == 'A1' and
            publication['status'] == outcome['status'] and
            receipt['status'] == 'complete' and receipt['terminal'] is True and
            Path(receipt['path']).resolve() == terminal_path.resolve() and
            receipt['sha256'] == receipt['worker']['sha256'] == expected_sha and
            receipt['worker']['pid'] == source['pid'] and receipt['worker']['bytes'] == receipt['bytes'] and
            receipt['bytes'] == paths['slots/A1/TERMINAL_SOURCE.json']['bytes'],
            'terminal_not_bound_to_real_published_slot')
    require(source['kind'] == 'actual_owned_Blender_evaluated_mesh' and
            source['asset_sha256'] == config['asset_sha256'] == asset_sha == digest(copy) and
            Path(source['asset_copy']).resolve() == Path(config['asset_copy']).resolve() == native_copy and
            source['frame'] == 1 and source['subframe'] == 0 and source['scale_length'] == 1.0 and
            all(terminal['display_object_mask']), 'wrong_current_asset_or_coordinates')
    require(pins.bytes(config['asset'], asset_sha) == copy, 'scene_original_does_not_match_owned_copy')
    scene = {'objects': [{'name': mesh['name'], 'vertices': mesh['evaluated']['vertices_world_m'],
                          'triangles': mesh['evaluated']['triangles']} for mesh in terminal['objects']]}
    require(len({mesh['name'] for mesh in scene['objects']}) == size[0] and len(scene['objects']) == size[0] and
            sum(len(mesh['vertices']) for mesh in scene['objects']) == size[1] and
            sum(len(mesh['triangles']) for mesh in scene['objects']) == size[2], 'saved_scene_denominator_changed')
    return scene, {'terminal_source_sha256': expected_sha, 'source_asset_sha256': asset_sha,
                   'original_slot_status': outcome['status'], 'source_export_status': receipt['status']}, bound


def load_installed(pins, binding_path):
    binding = pins.read(binding_path)
    install = Path(binding['install_root']).resolve()
    sys.path[:0] = [str(install), binding['dependency_root']]
    from human_eye_plugin import active_observation as api
    from human_eye_plugin.active_observation_host import freeze_cameras
    from human_eye_plugin.active_observation_images import _meshes_from_objects

    require(len(binding['source_manifest']) == 143, 'wrong_installed_manifest')
    for module in ('active_observation.py', 'active_observation_region_task.py',
                   'active_observation_host.py', 'active_observation_images.py'):
        name = 'human_eye_plugin/' + module
        row, = [row for row in binding['source_manifest'] if row['path'] == name]
        pins.bytes(install / name, row['sha256'])
    require(Path(api.__file__).resolve() == install / 'human_eye_plugin/active_observation.py',
            'imported_unregistered_product')
    return binding, api, freeze_cameras, _meshes_from_objects


def arguments(api, scene, cameras):
    objects, triangles, identity = api.geometry(scene)
    regions, scope = api.partition_regions(objects)
    return (objects, triangles, identity, regions, cameras), scope


def independent_certificate(api, triangles, cameras):
    points = {vertex for tri in triangles for vertex in tri.vertices}
    if not points:
        return {}, 0
    extrema = tuple((min(p[i] for p in points), max(p[i] for p in points)) for i in range(3))
    corners = tuple(product(*extrema))
    minima = {}
    for camera in cameras['views']:
        # Enumerate the eight corners rather than relying on the candidate's sign choice.
        planes = api.camera_planes(camera)
        minima[camera['name']] = min(
            sum(corner[i] * coefficients[i] for i in range(3)) + coefficients[3]
            for corner in corners for coefficients in planes)
    return minima, len(points)


def observed_build(api, args, scope, *, candidate=False, proof=False):
    real_shadow, real_distances = api.triangle_shadow, api.plane_distances
    real_planes, real_region = api.camera_planes, api.inside_frustum
    observations = {}
    current = None
    in_shadow = False

    def camera_planes(camera):
        nonlocal current
        current = observations.setdefault(camera['name'], Counter())
        return real_planes(camera)

    def region_frustum(points, planes):
        require(len(planes) == 6, 'region_frustum_denominator_changed')
        current['region_own_frustum_calls'] += 1
        return real_region(points, planes)

    def plane_distances(points, plane):
        values = real_distances(points, plane)
        if in_shadow:
            current['triangle_frustum_plane_checks'] += 1
            current['triangle_frustum_clips'] += int(min(values) < 0)
        return values

    def shadow(triangle, region, basis, planes, cached_screen=None):
        nonlocal in_shadow
        require(len(planes) in (0, 6), 'partial_triangle_frustum_scope')
        current['bypassed_shadow_calls' if not planes else 'legacy_shadow_calls'] += 1
        in_shadow = True
        try:
            return real_shadow(triangle, region, basis, planes, cached_screen)
        finally:
            in_shadow = False

    work = {}
    kwargs = {'prove_frustum_containment': proof, 'frustum_work': work} if candidate else {}
    with (patch.object(api, 'triangle_shadow', shadow), patch.object(api, 'plane_distances', plane_distances),
          patch.object(api, 'camera_planes', camera_planes), patch.object(api, 'inside_frustum', region_frustum)):
        index = api.build_index_from_parsed(*args, patch_scope=scope, **kwargs)
    totals = sum(observations.values(), Counter())
    if candidate and proof:
        require(totals['bypassed_shadow_calls'] == work['frustum_shadow_bypassed'] and
                totals['legacy_shadow_calls'] == work['frustum_shadow_legacy'] and
                work['frustum_certified_views'] + work['frustum_fallback_views'] == len(args[-1]['views']),
                'internal_counters_disagree_with_executed_shadow_paths')
    return index, {'views': {name: dict(counts) for name, counts in observations.items()},
                   'totals': dict(totals), 'candidate_counters': work}


def camera(scale=None):
    matrix = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    projection = [line.copy() for line in matrix]
    if scale == 'oblique':
        projection[0][1] = 1
    return {'views': [{'name': 'SCENE', 'direction_rational': [0, 0, 1], 'view_matrix': matrix,
                       'projection_matrix': projection, 'size_px': [512, 512]}]}


def cases(api, candidate):
    q = Fraction(1, 4)
    h = Fraction(1, 2)
    eps = Fraction(1, 2 ** 48)
    cases = (
        ('exact_positive_z_plane', [(-q, -q, 1), (q, -q, 1), (0, q, 1)], True, True),
        ('just_outside_x_plane', [(-q, -q, h), (1 + eps, -q, h), (0, q, h)], False, True),
        ('cross_near_far_planes', [(-q, -q, -2), (q, -q, 2), (0, q, h)], False, True),
        ('outside_entire_front', [(-q, -q, 2), (q, -q, 2), (0, q, 2)], False, False),
        ('cut_edge_zero_area', [(q, 3*q, h), (3*q, q, h), (3*q, 3*q, h)], True, False),
        ('opposite_depth', [(-q, -q, -h), (q, -q, -h), (0, q, -h)], True, False),
        ('partial_depth_occlusion', [(-q, -q, -h), (q, -q, h), (0, q, h)], True, True),
        ('degenerate_line', [(-q, -q, h), (0, 0, h), (q, q, h)], True, False),
        ('conservative_box_corner_fails', [(3*q, 0, h), (0, 3*q, h), (0, 0, h)], False, True),
        ('empty', None, False, False),
        ('region_still_outside', [(-q, -q, h), (q, -q, h), (0, q, h)], True, False),
    )
    reports = {}
    for name, vertices, certified, hidden in cases:
        base = {'name': 'receiver', 'vertices': [(-h, -h, 0), (h, -h, 0), (h, h, 0), (-h, h, 0)],
                'triangles': [(0, 1, 2), (0, 2, 3)]}
        objects = [] if vertices is None else [base, {'name': 'occluder', 'vertices': vertices,
                                                         'triangles': [(0, 1, 2)]}]
        args, scope = arguments(api, {'objects': objects},
                                camera('oblique' if name == 'conservative_box_corner_fails' else None))
        if name == 'region_still_outside':
            receiver, = args[3]
            receiver = replace(receiver, vertices=tuple((x, y, z+2) for x, y, z in receiver.vertices))
            args = (*args[:3], (receiver,), args[4])
        minimum, _ = independent_certificate(api, args[1], args[-1])
        require(bool(minimum and minimum['SCENE'] >= 0) == certified, 'independent_control_fixture/' + name)
        old, old_work = observed_build(api, args, scope, candidate=candidate)
        new, work = observed_build(api, args, scope, candidate=candidate, proof=candidate)
        require(asdict(old) == asdict(new), 'exact_synthetic_index_differs/' + name)
        expected = ('outside_frustum' if name == 'region_still_outside'
                    else 'positive_area_occlusion' if hidden else 'complete')
        classifications = list(new.classifications['SCENE'].values())
        require((not classifications if name == 'empty' else [row['status'] for row in classifications] == [expected]),
                'unproved_expected_synthetic_result/' + name)
        if candidate and vertices is not None:
            totals = Counter(work['totals'])
            old_totals = Counter(old_work['totals'])
            require(totals['region_own_frustum_calls'] == old_totals['region_own_frustum_calls'] == 1,
                    'region_exact_frustum_changed/' + name)
            if name != 'region_still_outside':
                require(totals['bypassed_shadow_calls' if certified else 'legacy_shadow_calls'] > 0,
                        'not_exercised_expected_shadow_path/' + name)
            if name in ('just_outside_x_plane', 'cross_near_far_planes', 'outside_entire_front'):
                minimum_clips = 2 if name == 'cross_near_far_planes' else 1
                require(totals['triangle_frustum_clips'] >= minimum_clips,
                        'outside_path_did_not_execute_actual_clip/' + name)
            if name == 'conservative_box_corner_fails':
                require(totals['triangle_frustum_plane_checks'] > 0 and not totals['triangle_frustum_clips'],
                        'conservative_failure_should_run_original_checks/' + name)
        reports[name] = {'box_minimum_plane_distance': {k: str(x) for k, x in minimum.items()},
                         'classification': classifications, 'index_sha256': object_digest(asdict(new)),
                         'old_observed_work': old_work, 'tested_observed_work': work}
    return reports


def benchmark(api, args, scope, candidate, repeats):
    rows = {'legacy': [], 'certified': []} if candidate else {'legacy': []}
    for ordinal in range(repeats):
        order = ('legacy', 'certified') if ordinal % 2 == 0 else ('certified', 'legacy')
        for name in order if candidate else ('legacy',):
            work = {}
            kwargs = {'prove_frustum_containment': name == 'certified', 'frustum_work': work} if candidate else {}
            started, cpu = time.perf_counter_ns(), time.process_time_ns()
            api.build_index_from_parsed(*args, patch_scope=scope, **kwargs)
            rows[name].append({'wall_ns': time.perf_counter_ns() - started,
                               'cpu_ns': time.process_time_ns()-cpu, **work})
    return {'pairs': repeats, 'samples': rows, 'medians': {
        name: {key: statistics.median(item[key] for item in samples) for key in ('wall_ns', 'cpu_ns')}
        for name, samples in rows.items()}}


def check_real_scene(api, get_cameras, meshes, scene, size, bound, candidate, repeats):
    objects, _, _ = api.geometry(scene)
    cameras = get_cameras(meshes(objects))
    args, scope = arguments(api, scene, cameras)
    require(len(args[3]) == size[3], 'different_partition_support_denominator')
    minima, points = independent_certificate(api, args[1], cameras)
    require(len(minima) == 6 and all(value >= 0 for value in minima.values()), 'actual_fixture_lost_full_certificate')
    old, old_work = observed_build(api, args, scope, candidate=candidate)
    current, work = observed_build(api, args, scope, candidate=candidate, proof=candidate)
    require(asdict(old) == asdict(current), 'exact_real_coverage_index_changed')
    if candidate:
        require(work['candidate_counters']['frustum_certified_views'] == 6 and
                work['candidate_counters']['frustum_fallback_views'] == 0 and
                not work['totals'].get('triangle_frustum_plane_checks') and
                work['totals']['bypassed_shadow_calls'] == old_work['totals']['legacy_shadow_calls'] and
                work['totals']['region_own_frustum_calls'] == old_work['totals']['region_own_frustum_calls'],
                'actual_scene_certificate_did_not_bypass_exactly_the_triangle_checks')
    locals_seen = {}
    if size[0] == 21:
        producer = bound('product_full/call_001/SERVICE_RESULT.json')
        require(producer['binding']['camera_specification'] == cameras,
                'generated_global_cameras_differ_from_original_installed_producer')
        for local in producer['scopes']:
            local_binding = local['binding']
            if local['scope_id'] == 'global':
                continue
            camera_spec = local_binding['camera_specification']
            roi, = local['facts']['regions']
            region, = [r for r in args[3] if r.roi_id == roi['roi_id']]
            alternate_args = (*args[:3], (region,), camera_spec)
            local_minima, _ = independent_certificate(api, args[1], camera_spec)
            original_local, original_work = observed_build(api, alternate_args, (), candidate=candidate)
            tested_local, local_work = observed_build(api, alternate_args, (), candidate=candidate, proof=candidate)
            require(asdict(original_local) == asdict(tested_local) and len(local_minima) == 6 and
                    all(value < 0 for value in local_minima.values()) and
                    local_work['totals'].get('legacy_shadow_calls', 0) > 0,
                    'actual_local_fallback_not_exercised')
            if candidate:
                require(local_work['candidate_counters']['frustum_fallback_views'] == 6 and
                        local_work['candidate_counters']['frustum_shadow_bypassed'] == 0,
                        'actual_local_camera_did_not_retain_original_triangle_path')
            locals_seen[region.object_name] = {'original_work': original_work, 'tested_work': local_work,
                'coverage_sha256': object_digest(asdict(tested_local)),
                'independent_plane_minima': {name: str(v) for name, v in local_minima.items()}}
        require(set(locals_seen) == {'M02', 'M09'}, 'missing_actual_local_camera_pair')
    return {'counts': {'objects': size[0], 'vertices': size[1], 'unique_triangle_points': points,
                       'triangles': size[2], 'supported_rectangles': size[3]},
            'coverage_sha256': object_digest(asdict(current)),
            'exact_cameras_sha256': object_digest(cameras),
            'independent_plane_minima': {name: str(v) for name, v in minima.items()},
            'positive_area_rows': sum(row['status'] == 'positive_area_occlusion'
                                      for rows in current.classifications.values() for row in rows.values()),
            'observed_legacy_work': old_work, 'observed_tested_work': work,
            'local_negatives': locals_seen, 'direct_index_timing': benchmark(api, args, scope, candidate, repeats)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--repeats', type=int, default=3, choices=range(2, 7))
    cli = parser.parse_args()
    pins = Pins()
    pins.bytes(__file__)
    pins.bytes(Path(sys.executable))
    pins.bytes(FORMAL / 'fixture/CURRENT_TRUTH.json', TRUTH_SHA)
    binding, api, get_cameras, meshes = load_installed(pins, cli.binding)
    candidate = 'prove_frustum_containment' in inspect.signature(api.build_index_from_parsed).parameters
    require(candidate == (cli.baseline is not None), 'candidate_requires_sealed_installed_baseline')
    synthetic = cases(api, candidate)
    results = {}
    for key, runtime, evidence, asset, size in TWO_RUNS:
        scene, provenance, bound = sealed_capture(pins, runtime, evidence, asset, size)
        results[key] = provenance | check_real_scene(api, get_cameras, meshes, scene, size, bound, candidate,
                                                     cli.repeats)
    if candidate:
        old = pins.read(cli.baseline)
        require(old['passed'] and old['baseline'] and old['runtime_source_sha256'] != binding['source_sha256'],
                'separate_installed_baseline_receipt_required')
        for key in synthetic:
            require(old['synthetic'][key]['index_sha256'] == synthetic[key]['index_sha256'],
                    'installed_baseline_control_differs/' + key)
        for key, result in results.items():
            require(all(old['scenes'][key][k] == result[k] for k in
                        ('counts', 'coverage_sha256', 'exact_cameras_sha256', 'terminal_source_sha256')) and
                    {k: v['coverage_sha256'] for k, v in old['scenes'][key]['local_negatives'].items()} ==
                    {k: v['coverage_sha256'] for k, v in result['local_negatives'].items()},
                    'installed_baseline_exact_scene_differs/' + key)
    result = {'schema': 'm4-cold-frustum-installed-offline-v1', 'passed': True, 'baseline': not candidate,
              'product_root': binding['install_root'], 'runtime_source_sha256': binding['source_sha256'],
              'owned_Blender': 0, 'models': 0, 'actual_new_rasters': 0, 'scenes': results,
              'synthetic': synthetic, 'source_pins': list(pins.entries.values())}
    with cli.output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': True, 'baseline': not candidate, 'destination': str(cli.output),
                      'scene_medians': {k: v['direct_index_timing']['medians'] for k, v in results.items()}}))


if __name__ == '__main__':
    main()
