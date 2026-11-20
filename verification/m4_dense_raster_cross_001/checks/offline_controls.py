"""Prove raster equivalence against trusted archived pixels and fixed controls."""

import argparse
import hashlib
from io import BytesIO
import itertools
import json
from pathlib import Path
import runpy
from statistics import median
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NS = HERE.parent
V = NS.parent
BASE = V / 'm4_global_pixel_bound_short_circuit_001'
PRIOR = BASE / 'checks/offline_controls.py'
DISPLAY = V / 'm4_source_region_display_001/tests/test_display_images.py'
SOURCE = 'human_eye_plugin/attention_raster.py'
DENSE = ('dense', 'm4_global_pixel_bound_short_circuit_001', 'B1',
         'c412558ed01216ffed1dff1634112cb95a2fd70469ca049d86874e5c8ba15a9e', 1, (14, 3478, 6148))
ARR_SHORT = ('color', 'depth', 'owners', 'triangle_ids')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def encode(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':'), sort_keys=True).encode()


def require(value, message):
    if not value:
        raise ValueError(message)


def bind_archives(prior, pins, archive, baseline):
    make = prior['archived_cases']
    make.__globals__['FIXTURES'] = (DENSE, *[row for row in prior['FIXTURES'] if row[0] != 'dense'])
    return make(pins, archive, baseline)


def frame_bytes(frame):
    return {'scope_id': frame.get('scope_id'),
            **{key: frame[key] for key in ('view_name', 'image_sha256', 'arrays_sha256')}}


def fingerprint(value, root):
    """Keep all evidence fields while normalizing temporary paths and profiling clocks."""
    if isinstance(value, dict):
        return {key: fingerprint(item, root) for key, item in value.items()
                if key not in ('stages', 'feedback_stages', 'generation_stages', 'frustum_proof_ns')}
    if isinstance(value, list):
        return [fingerprint(item, root) for item in value]
    if isinstance(value, str) and value.startswith(str(root)):
        return Path(value).relative_to(root).as_posix()
    return value


def raw_array(array):
    return {'sha256': sha(array.tobytes()), 'dtype': array.dtype.str, 'shape': list(array.shape)}


def saved_raster(np, frame, arrays, raw_ids, meshes, raster):
    size = frame['pose']['size_px'][0]
    pose = frame['pose']
    view, projection = (np.asarray(pose[name], dtype=np.float64) for name in ('view_matrix', 'projection_matrix'))
    if 'display_object_mask' in arrays:
        mask = tuple(bool(value) for value in arrays['display_object_mask'])
        options = {'object_mask': mask}
    else:
        options = {}
    actual = raster(meshes, view, projection, size, return_owner=True, return_patch_owner=True,
                    face_patch_ids=raw_ids, **options)
    observed = dict(zip(ARR_SHORT, actual, strict=True))
    require(all(raw_array(value) == raw_array(arrays[key]) for key, value in observed.items()), 'raw_pixel_change')
    patches = np.full((size, size), -1, dtype=np.int32)
    foreground = observed['triangle_ids'] >= 0
    patches[foreground] = arrays['face_patch_ids'][observed['triangle_ids'][foreground]]
    require(raw_array(patches) == raw_array(arrays['patch_owners']), 'raw_patch_owner_change')
    return {key: raw_array(value) for key, value in (*observed.items(), ('patch_owners', patches))}


def geometry_inputs(core, host, images, capture):
    objects, _, _ = core.geometry(host.scene_from_capture(capture))
    return images._meshes_from_objects(objects)


def region_replay(np, core, host, images, regions, mcp, prior, inputs, base):
    regions_replayed = {}
    for name, case in inputs.items():
        archive = case['cold']
        root = base / name
        root.mkdir()
        capture = case['capture']
        meshes = geometry_inputs(core, host, images, capture)
        offsets = np.array([0, *itertools.accumulate(len(mesh.faces) for mesh in meshes)])
        raw_ids = tuple(np.arange(lo, hi, dtype=np.int32) for lo, hi in zip(offsets[:-1], offsets[1:]))
        reference = archive['producer']
        direct = []
        for frame in reference['constructed_frames']:
            array_data = Path(frame['arrays_path']).read_bytes()
            png_data = Path(frame['image_path']).read_bytes()
            require(sha(array_data) == frame['arrays_sha256'] and sha(png_data) == frame['image_sha256'],
                    'retained_arrays_or_png_changed/' + name)
            with np.load(BytesIO(array_data), allow_pickle=False) as arrays:
                direct.append(saved_raster(np, frame, arrays, raw_ids, meshes, images.rasterize_attention))
        retained = []
        decide = []
        def reuse_index(build):
            if retained:
                return retained[0], True
            value = build()
            retained.append(value)
            return value, False

        conditions = archive['arguments']['query']['region_task']
        actual = regions.observe_region_task(capture, root, conditions,
                         construction_callback=decide.append, prepare_global_index=reuse_index)
        prior['compare_archived'](actual, reference)
        require(decide == [f['view_name'] for f in reference['constructed_frames']], 'actual_coverage_order_change')
        predicted = regions.observe_region_task(capture, root, conditions, include_image=False,
                            prepare_global_index=reuse_index)
        require(predicted['status'] == 'predicted' and predicted['observation_status'] == 'prediction_only'
                and predicted['work']['global_index_cache_hit'] and not predicted['constructed_frames']
                and predicted['work']['raster_attempts'] == predicted['work']['pixel_bound_region_calls'] == 0
                and predicted['binding'] == actual['binding'], 'same_generation_prediction_change')
        if case['hot'] is not None:
            prior['compare_archived'](predicted, case['hot']['producer'])
        brief = prior['render_payload'](mcp, actual, reference, 'brief')
        full = prior['render_payload'](mcp, actual, reference, 'full')
        no_image = prior['render_payload'](mcp, predicted, reference, 'full')
        require(all(raw['isError'] is False for raw in (brief, full, no_image))
                and brief['content'][1:] == archive['original_result']['content'][1:]
                and len(no_image['content']) == 1, 'changed_region_delivery/' + name)
        if name == 'dense':
            text, saved = (wire['content'][0]['text'] for wire in (brief, archive['original_result']))
            parsed, original = map(json.loads, (text, saved))
            if parsed != original or len(text.encode()) != len(saved.encode()):
                raise ValueError('exact_dense_brief_changed/' + prior['first_difference'](parsed, original))
        def wire_hash(reply):
            fact, *pngs = reply['content']
            return sha(encode([fingerprint(json.loads(fact['text']), root), *pngs]))

        regions_replayed[name] = {
            'source_counts': case['counts'], 'asset_sha256': case['asset_sha256'],
            'frames': [frame_bytes(frame) for frame in actual['constructed_frames']],
            'exact_archived_buffers': direct,
            'region_facts_sha256': sha(encode(actual['facts']['region_task'])),
            'original_wire_sha256': archive['wire_sha256'],
            'brief_sha256': wire_hash(brief), 'full_sha256': wire_hash(full),
            'same_capture_no_image_full_sha256': wire_hash(no_image),
            'same_capture_no_image_zero_raster': True,
            'skip_certificate_sha256': sha(encode([scope['skipped_views'] for scope in actual['scopes']])),
        }
    return regions_replayed


def synthetic_cases(np, raster, mesh_type):
    def mesh(name, vertices, color=(217, 81, 147), faces=((0, 1, 2),)):
        return mesh_type(name, '#' + name, name, np.array(vertices, dtype=np.float64),
                         np.array(faces, dtype=np.int32), None, color, False,
                         local_axes=np.eye(3), axes_source='world_geometry',
                         axes_confidence='explicit', axes_reason='world_coordinates_no_transform')

    view = np.eye(4)
    projection = np.diag([1., 1., -.2, 1.])
    front = [[-.75, -.75, -1.], [.75, -.75, -1.], [0, .75, -1.]]
    back = [[x, y, z - 1] for x, y, z in front]
    near = [[-3, -.5, -.01], [.6, -2., -2.], [0., 3., -7.]]
    exact = [[-1, -1, -5], [1, -1, -5], [0, 1, -5]]
    tie_a = mesh('tie-a', front, (252, 4, 63))
    tie_b = mesh('tie-b', front, (5, 62, 249))
    normal = mesh('normal', front)
    behind = mesh('back', back)
    degenerate = mesh('zero-scale', [[-0., 0., -1.], [-0., 0., -1.], [-0., 0., -1.]])
    collinear = mesh('zero-area', [[-.5, -.5, -1.], [0., 0., -1.], [.5, .5, -1.]])
    large = mesh('huge', [[-1e200, -.6, -1.5], [1e200, -.5, -1.5], [0, 1e200, -1.5]])
    tiny = mesh('tiny', [[1e-280, -2e-280, -1.], [2e-280, 2e-280, -1.], [0., 0., -1.]])
    overflow = mesh('overflow', [[-1e308, 0., -1.], [1e308, 0., -1.], [0., .5, -1.]])
    mappings = (np.array([-1], dtype=np.int32), np.array([9], dtype=np.int32))
    configurations = {
      'ordinary_without_owner': ((normal, behind), {}),
      'ordinary_with_owner': ((normal, behind), {'return_owner': True}),
      'exact_clip_plane': ((mesh('boundary', exact),), {'return_owner': True}),
      'near_far_side_clip': ((mesh('near', near),), {'return_owner': True}),
      'coincident_depth_retains_first': ((tie_a, tie_b), {'return_owner': True}),
      'coincident_depth_reverse_order': ((tie_b, tie_a), {'return_owner': True}),
      'zero_scale_degenerate_collinear': ((degenerate, collinear, normal), {'return_owner': True}),
      'extreme_finite_scale': ((large, tiny, normal), {'return_owner': True}),
      'unsupported_source_keeps_depth': ((normal, behind),
          {'return_owner': True, 'return_patch_owner': True, 'face_patch_ids': mappings}),
      'hidden_front_changes_visible_owner': ((normal, behind),
          {'return_owner': True, 'return_patch_owner': True, 'face_patch_ids': mappings, 'object_mask': (False, True)}),
    }
    results = {}
    for name, (meshes, options) in configurations.items():
        data = raster.rasterize_attention(meshes, view, projection, 64, **options)
        results[name] = [raw_array(value) for value in data]
    require(results['coincident_depth_retains_first'][0] != results['coincident_depth_reverse_order'][0] and
            results['hidden_front_changes_visible_owner'][2] != results['unsupported_source_keeps_depth'][2],
            'controls_failed_to_affect_raster_visibility')
    expected = {
        'geometry_limit': 'Attention raster geometry work budget exceeded',
        'sample_limit': 'Attention raster pixel work budget exceeded',
        'numeric_overflow': 'Attention raster geometry exceeds numeric range',
    }
    for name, work, meshes, matrix in (
            ('geometry_limit', patch.object(raster, 'work_budget_status', return_value={'within_budget': False}),
             [normal], projection),
            ('sample_limit', patch.object(raster, 'MAX_PIXEL_SAMPLES', 1), [normal], projection),
            ('numeric_overflow', patch.object(raster, 'MAX_PIXEL_SAMPLES', raster.MAX_PIXEL_SAMPLES),
             [overflow], np.diag([1e-308, 1., -.2, 1.]))):
        with work:
            try:
                raster.rasterize_attention(meshes, view, matrix, 64)
            except ValueError as exc:
                require(str(exc) == expected[name], 'rejection_reason_changed/' + name)
                results[name] = str(exc)
            else:
                raise ValueError('expected_raster_rejection_missing/' + name)

    # Inject no arithmetic. Intercept length input after each genuine product
    # face cross so sign bits are checked even on triangles with no sample.
    rng = np.random.default_rng(210032)
    normals = []
    first_face_points = [[[-0., -0., -0.], [0., -0., 0.], [-0., 0., -0.]],
                         [[-0., -0., -0.], [0., -0., 1.], [-0., 0., 0.]],
                         [[0., 0., 0.], [0., 0., 1e-300], [-0., 0., -0.]]]
    first_face_points.extend(np.ldexp(rng.uniform(-1, 1, size=(64, 3, 3)),
                                       rng.integers(-1000, 660, size=(64, 1, 3))).tolist())
    normal_count = len(first_face_points)
    all_vertices = np.asarray(first_face_points, dtype=np.float64).reshape(-1, 3)
    faces = np.arange(len(all_vertices)).reshape(-1, 3)
    controlled = mesh('sign-bit-capture', all_vertices, faces=faces)
    # Keep depth arithmetic and viewport distances small even for wide worlds.
    # Existing area rules may discard coverage after we inspect every normal.
    def length(value):
        normals.append(np.array(value, dtype=np.float64))
        return norm(value)

    norm = np.linalg.norm
    with patch.object(raster.np.linalg, 'norm', side_effect=length):
        raster.rasterize_attention([controlled], view, np.diag([1e-200, 1e-200, 1e-200, 1.]), 64)
    require(len(normals) == normal_count + 1 and len(normals[1:]) == len(faces),
            'wide_control_normals_not_all_sampled')
    got = np.asarray(normals[1:])
    oracle = []
    for face in controlled.faces:
        triangle = controlled.vertices[face]
        u, v = triangle[1] - triangle[0], triangle[2] - triangle[0]
        scale = max(float(np.max(np.abs(u))), float(np.max(np.abs(v))))
        oracle.append(np.cross(u / scale, v / scale) if scale else np.zeros(3))
    require(raw_array(got) == raw_array(np.asarray(oracle)), 'normal_bits_or_signed_zero_changed')
    require(np.any(np.signbit(got[got == 0.])), 'negative_zero_not_exercised')
    results['normal_oracle'] = {'cases': normal_count, 'bits': raw_array(got),
                                'negative_zero_components': int(np.count_nonzero(np.signbit(got[got == 0.])))}
    return results


def ordinary_and_explicit(host, source, mcp, tmp):
    fixture = runpy.run_path(str(DISPLAY))
    out = {}
    for label, capture in (
            ('ordinary', fixture['captured']((True, True, True))),
            ('explicit_target', fixture['captured']((False, True, True))),
            ('explicit_target_hidden', fixture['captured']((True, False, True)))):
        directory = tmp / label
        directory.mkdir()
        if label == 'ordinary':
            result = host.observe_capture(capture, directory)
            extra = {}
        else:
            prepared = source.prepare_region(capture,
                {'region': {'object': {'name': 'Body'}, 'source_triangle_indices': [1]}})
            result = source.observe_region(prepared, directory, include_image=True)
            result['task_result'] = source.measure_region(prepared, {'name': 'Ref'}, None)
            reused = source.observe_region(prepared, directory, include_image=True)
            no_image = source.observe_region(prepared, directory, include_image=False)
            require(reused['frames'] == result['frames'] and reused['work']['raster_attempts'] == 0
                    and not no_image['frames'] and no_image['work']['raster_attempts'] == 0,
                    'explicit_region_reuse_or_no_image_changed/' + label)
            extra = {'same_generation_frame_reuses': reused['work']['frame_reuses'],
                     'no_image_new_raster_attempts': no_image['work']['raster_attempts']}
        frames = result.get('frames', [])
        status = 'partial' if label == 'explicit_target_hidden' else 'complete'
        require(result['status'] == status and len(frames) > 0, 'ordinary_or_explicit_missing_frames/' + label)
        if label == 'explicit_target_hidden':
            require(result['facts']['visibility']['reason'] == 'selected_region_not_displayed',
                    'explicit_hidden_target_visibility_claimed')
        for frame in frames:
            require(sha(Path(frame['image_path']).read_bytes()) == frame['image_sha256'] and
                    sha(Path(frame['arrays_path']).read_bytes()) == frame['arrays_sha256'], 'synthetic_frame_binding_drift')
        formatted = mcp._tool_result(result, is_error=False, response_detail='brief')
        require(formatted['isError'] is False and len(formatted['content']) == len(frames) + 1,
                'ordinary_or_explicit_native_schema_changed/' + label)
        body, *attachments = formatted['content']
        out[label] = {'frames': [frame_bytes(row) for row in frames], **extra,
                      'facts': sha(encode(fingerprint(result, directory))),
                      'wire': sha(encode([fingerprint(json.loads(body['text']), directory), *attachments]))}
    return out


def worker(binding_path, mode):
    binding = read(binding_path)
    install = Path(binding['install_root']).resolve()
    sys.path[:0] = [str(install), binding['dependency_root']]
    import numpy as np
    from human_eye_module1_operators import MeshEntity3D
    from human_eye_plugin import active_observation as core, active_observation_host as host
    from human_eye_plugin import active_observation_images as images, active_observation_region_task as regions
    from human_eye_plugin import attention_raster as raster, live_spatial_mcp as mcp, source_region

    loaded = Path(raster.__file__).resolve()
    manifest_sha = next(row['sha256'] for row in binding['source_manifest'] if row['path'] == SOURCE)
    require(loaded == install / SOURCE and sha(loaded.read_bytes()) == manifest_sha,
            'raster_not_the_registered_install')
    require(images.rasterize_attention is raster.rasterize_attention,
            'region_does_not_call_installed_raster')
    inputs = json.load(sys.stdin)
    if mode == 'timing':
        meshes = geometry_inputs(core, host, images, inputs['capture'])
        offsets = [0, *itertools.accumulate(len(mesh.faces) for mesh in meshes)]
        mapping = [np.arange(lo, hi, dtype=np.int32) for lo, hi in zip(offsets[:-1], offsets[1:])]
        views = [(p['name'], np.asarray(p['view_matrix']), np.asarray(p['projection_matrix'])) for p in inputs['poses']]
        require([name for name, _, _ in views] == ['SCENE', 'LEFT'], 'registered_two_dense_views_required')
        def timed():
            times = {}
            for name, view, projection in views:
                started = time.perf_counter_ns()
                output = raster.rasterize_attention(meshes, view, projection, 512, return_owner=True,
                    return_patch_owner=True, face_patch_ids=mapping)
                times[name] = time.perf_counter_ns() - started
                require(len(output) == 4, 'timing_no_production_buffers')
            return times
        warm = timed()
        measured = timed()
        result = {'elapsed_ns': measured, 'warmup_elapsed_ns': warm}
    else:
        prior = runpy.run_path(str(PRIOR))
        with tempfile.TemporaryDirectory(prefix='he-raster-bits-') as scratch:
            base = Path(scratch).resolve()
            fixtures = region_replay(np, core, host, images, regions, mcp, prior, inputs, base)
            results = synthetic_cases(np, raster, MeshEntity3D)
            entrypoints = ordinary_and_explicit(host, source_region, mcp, base)
        result = {'archived_fixtures': fixtures, 'synthetic': results, 'actual_entrypoints': entrypoints}
    print(json.dumps({'source_sha256': binding['source_sha256'], 'raster_source_sha256': manifest_sha,
                      'numpy_version': np.__version__, **result}, sort_keys=True, ensure_ascii=True))


def launch(path, mode, inputs):
    argv = [sys.executable, '-IB', str(Path(__file__).resolve()), '--worker', mode, str(path)]
    child = subprocess.run(argv, input=encode(inputs), capture_output=True, timeout=120)
    if child.returncode:
        raise RuntimeError(child.stderr.decode(errors='replace'))
    return json.loads(child.stdout)


def parent(candidate_path, output):
    old_binding = BASE / 'install/PRODUCT_RUN_BINDING.json'
    priors = runpy.run_path(str(PRIOR))
    archive = runpy.run_path(str(priors['ARCHIVE_HELPER']))
    projection = runpy.run_path(str(archive['PRIOR']))
    pins = projection['Evidence']()
    for path in (Path(__file__), PRIOR, priors['ARCHIVE_HELPER'], priors['CAPTURE_HELPER'],
                 archive['PRIOR'], DISPLAY, old_binding, candidate_path):
        pins.raw(path)
    bindings = {label: read(path) for label, path in (('A', old_binding), ('B', candidate_path))}
    manifests = [{row['path']: row['sha256'] for row in install['source_manifest']} for install in bindings.values()]
    a, b = manifests
    require(bindings['A']['preparation_git'] == 'f72e648f763fb6399f82c8e5d7f2b35840597bed'
            and a.keys() == b.keys() and len(a) == 143 and [key for key in a if a[key] != b[key]] == [SOURCE],
            'raster_candidate_changed_more_than_the_single_frozen_source')
    for arm, manifest in zip(bindings.values(), manifests, strict=True):
        for path in (SOURCE, 'human_eye_plugin/active_observation_images.py',
                     'human_eye_plugin/active_observation_host.py', 'human_eye_plugin/active_observation_region_task.py',
                     'human_eye_plugin/source_region.py', 'human_eye_plugin/live_spatial_mcp.py'):
            pins.raw(Path(arm['install_root']) / path, manifest[path])
    cases = bind_archives(priors, pins, archive, bindings['A'])
    arms = {'A': old_binding, 'B': candidate_path}
    body = {}
    for arm, path in arms.items():
        body[arm] = launch(path, 'equivalence', cases)
    metrics = ('archived_fixtures', 'synthetic', 'actual_entrypoints')
    for key in metrics:
        if body['A'][key] != body['B'][key]:
            raise ValueError('installed_outputs_changed/' + priors['first_difference'](body['A'][key], body['B'][key], key))
    require(body['A']['numpy_version'] == body['B']['numpy_version'] == '2.3.5',
            'installed_numpy_dependency_changed')
    dense = cases['dense']
    bound = {'capture': dense['capture'], 'poses': [frame['pose'] for frame in dense['cold']['producer']['constructed_frames']]}
    orders = ('AB', 'BA', 'AB', 'BA', 'AB')
    timing = []
    for sequence in orders:
        slot = {arm: launch(arms[arm], 'timing', bound) for arm in sequence}
        a_time, b_time = (sum(slot[arm]['elapsed_ns'].values()) for arm in ('A', 'B'))
        timing.append({'order': sequence, 'results': slot, 'paired_net_saving_ns': a_time - b_time,
                       'paired_reduction_percent': 100 * (a_time - b_time) / a_time})
    speedup = median(row['paired_reduction_percent'] for row in timing)
    wins = sum(row['paired_net_saving_ns'] > 0 for row in timing)
    receipt = {'passed': wins >= 3 and speedup > 0, 'actual_Blender_processes': 0, 'actual_model_runs': 0,
               'actual_live_raster_attempts': 0, 'fixture_semantics': 'Original ZIP-matched scene and camera preimages, actual offline raster.',
               'equivalence': body, 'timing': timing, 'dense_positive_pairs': wins,
               'median_dense_two_raster_reduction_percent': speedup,
               'median_dense_two_raster_saving_ns': median(row['paired_net_saving_ns'] for row in timing),
               'synthetic_expected_rejection_types': ['geometry_limit', 'sample_limit', 'numeric_overflow'],
               'source_pins': [pins.pins[key] for key in sorted(pins.pins)]}
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(receipt, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')
    print('Offline raster receipt', sha(output.read_bytes()), 'paired median', speedup, 'paired wins', wins)
    return not receipt['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, default=NS / 'install/PRODUCT_RUN_BINDING.json')
    parser.add_argument('--output', type=Path, default=HERE / 'OFFLINE_CONTROLS.json')
    parser.add_argument('--worker', nargs=2)
    args = parser.parse_args()
    require(sys.flags.isolated and sys.dont_write_bytecode, 'registered_isolated_interpreter_required')
    if args.worker:
        mode, path = args.worker
        worker(path, mode)
    else:
        raise SystemExit(parent(args.candidate, args.output))
