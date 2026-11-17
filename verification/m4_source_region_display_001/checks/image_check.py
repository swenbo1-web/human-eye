"""Independently check saved display-scoped source-region deliveries.

The sealed preceding checker supplies saved-byte readers, source geometry
checks and numerical ray primitives. This module consumes JSON, PNG and NPZ
evidence, checks all foreground source memberships, RGB and depths, and casts
a fixed 16 by 16 grid plus all 748 selected-face centroid rays. It creates no
image, imports no product module and starts no Blender or model process.
"""

import argparse
import base64
from collections import Counter
from fractions import Fraction
import hashlib
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import sys
import time
import traceback


sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
NS = HERE.parent
REPO = HERE.parents[2]
PREVIOUS = REPO / 'verification/m4_real_asset_region_qualification_001/checks/image_check.py'
PREVIOUS_SHA = '1ad6fff952bac01a1a34ef3dd306cceff6ca8f6372f4bc795cf01d4326d7e012'
FIXED_PUBLIC = REPO / 'verification/m4_real_asset_region_qualification_001/runtime_archive/f000092_SERVICE_RESULT.json'
FIXED_PUBLIC_SHA = 'e5f6299fbef6600c847d4391c1767aeeb71bd492e7b398a793aeda13473556db'
if hashlib.sha256(PREVIOUS.read_bytes()).hexdigest() != PREVIOUS_SHA:
    raise ValueError('sealed_previous_image_checker_changed')
_spec = importlib.util.spec_from_file_location('_sealed_display_previous_image_checker', PREVIOUS)
OLD = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OLD)
SAVED = OLD.SAVED
np, Image, fingerprint = OLD.np, OLD.Image, OLD.fingerprint
GRID_SIDE = OLD.GRID_SIDE
DEPTH_ALLOWANCE_M = OLD.DEPTH_ALLOWANCE_M
DISPLAY_FIELDS = ('visible_get', 'hide_get', 'hide_viewport', 'hide_render')
SCHEMA = 'm4-source-region-display-saved-image-review-v1'


class Audit(OLD.Audit):
    def __init__(self):
        super().__init__()
        self.file(__file__)
        self.file(PREVIOUS, PREVIOUS_SHA)


def digest_json(value, *, ensure_ascii=False):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'),
                     ensure_ascii=ensure_ascii, allow_nan=False).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def display_checks(snapshot, capture, binding, audit):
    fresh = snapshot['display_snapshot']
    audit.check(fresh['source'] == 'current_owned_Blender_Object.visible_get(view_layer=current)'
                and fresh['scope'] == 'active_view_layer_effective_viewport'
                and fresh['viewport'] is None, 'fresh_explicit_current_view_layer_visible_get_source')
    audit.check(snapshot['display_snapshot_sha256'] == digest_json(fresh, ensure_ascii=True),
                'fresh_display_snapshot_digest_preimage')
    actual = capture['display_snapshot']
    unsigned = {key: value for key, value in actual.items() if key != 'sha256'}
    audit.check(actual['schema'] == 'blender-viewport-display-v1'
                and actual['scope'] == 'active_view_layer' and actual['status'] == 'captured'
                and actual['sha256'] == digest_json(unsigned), 'actual_current_host_display_snapshot_digest')
    layer = {key: fresh['view_layer'][key] for key in ('name', 'instance_id')}
    audit.check(actual['view_layer'] == layer and layer['instance_id'].startswith('rna:'),
                'fresh_current_active_view_layer_name_and_RNA_identity')
    fresh_rows = {row['host_id']: row for row in fresh['objects'] if row['type'] == 'MESH'}
    expected = []
    scope_objects = []
    for host in binding['objects']:
        row = fresh_rows[host['host_id']]
        audit.check(row['name'] == host['object_name'] and row['instance_id'] == host['instance_id']
                    and all(type(row[key]) is bool for key in DISPLAY_FIELDS),
                    'fresh_explicit_visibility_host_instance/' + row['name'])
        expected.append({key: row[key] for key in ('host_id', 'instance_id', *DISPLAY_FIELDS)})
        scope_objects.append({**host, 'participates': row['visible_get'],
            'reason': 'host_visible_get_true' if row['visible_get'] else 'host_visible_get_false',
            **{key: row[key] for key in DISPLAY_FIELDS}})
    audit.check(set(fresh_rows) == {row['host_id'] for row in binding['objects']}
                and actual['objects'] == sorted(expected, key=lambda row: row['host_id']),
                'fresh_all_mesh_display_flags_equal_actual_capture')
    mask = [row['visible_get'] for row in scope_objects]
    scope = dict(schema='human-eye-source-region-display-v1', status='captured',
        identity=actual['sha256'], scope='active_view_layer_effective_viewport', view_layer=layer,
        participation_source='blender.visible_get(view_layer=captured_active_view_layer)',
        hide_flag_scope=dict(hide_get='captured_view_layer', hide_viewport='object_viewport',
                             hide_render='object_render'),
        participation_mask=mask, objects=scope_objects,
        participating_object_indices=[index for index, value in enumerate(mask) if value],
        excluded_object_indices=[index for index, value in enumerate(mask) if not value],
        snapshot_sha256=actual['sha256'])
    audit.check(binding['display_identity'] == actual['sha256'] and binding['image_scope'] == scope,
                'binding_exact_fresh_host_display_scope_and_participation_preimage')
    return scope


def current_capture(captures, binding, audit):
    matches = [capture for capture in captures if capture['revision'] == binding['scene_revision']
        and capture['capture_state'] == binding['capture_state']
        and capture.get('capture_scope', 'complete_scene_meshes') == binding['capture_scope']
        and capture.get('display_snapshot', {}).get('sha256') == binding['display_identity']]
    audit.check(bool(matches), 'same_generation_and_current_display_original_capture_available')
    audit.check(len({fingerprint(capture) for capture in matches}) == 1,
                'same_generation_and_display_capture_unambiguous')
    return matches[0]


def participating_rays(origins, direction, triangles, participating, near, far):
    eligible = np.flatnonzero(participating)
    if not len(eligible):
        return np.full(len(origins), np.inf), np.full(len(origins), -1, dtype=np.int64), np.zeros(len(origins), dtype=bool)
    depths, winners, ambiguous = OLD.nearest_rays(origins, direction, triangles[eligible], near, far)
    hits = winners >= 0
    winners[hits] = eligible[winners[hits]]
    return depths, winners, ambiguous


def grid_checks(frame, arrays, triangles, object_ids, offsets, participating, audit):
    height, width = arrays['owners'].shape
    grid_x = np.floor((np.arange(GRID_SIDE) + .5) * width / GRID_SIDE).astype(int)
    grid_y = np.floor((np.arange(GRID_SIDE) + .5) * height / GRID_SIDE).astype(int)
    xs, ys = np.meshgrid(grid_x, grid_y)
    xs, ys = xs.ravel(), ys.ravel()
    origins, direction, inside = OLD.pixel_origins(xs, ys, frame['pose'])
    best, winners, ambiguous = participating_rays(origins, direction, triangles, participating,
                                                 frame['pose']['near'], frame['pose']['far'])
    best[~inside], winners[~inside] = np.inf, -1
    actual = arrays['triangle_ids'][ys, xs]
    foreground = actual >= 0
    audit.check(np.array_equal(winners >= 0, foreground), 'fixed_grid_display_nearest_foreground_mask')
    audit.check(np.all(np.abs(arrays['depth'][ys[foreground], xs[foreground]] - best[foreground])
                       <= DEPTH_ALLOWANCE_M), 'fixed_grid_no_nearer_participating_surface')
    certain = foreground & ~ambiguous
    audit.check(np.array_equal(actual[certain], winners[certain])
                and np.array_equal(arrays['owners'][ys[certain], xs[certain]], object_ids[winners[certain]]),
                'fixed_grid_unambiguous_global_source_face_and_object')
    rows = []
    for index, (x, y) in enumerate(zip(xs, ys, strict=True)):
        face = int(winners[index])
        owner = int(object_ids[face]) if face >= 0 else -1
        rows.append(dict(pixel=[int(x), int(y)], nearest_global_source_triangle=face,
            nearest_object_index=owner, nearest_local_source_triangle=int(face - offsets[owner]) if owner >= 0 else -1,
            camera_depth_m=float(best[index]) if face >= 0 else None,
            saved_global_source_triangle=int(actual[index]), boundary_or_depth_tie=bool(ambiguous[index])))
    denominator = int(participating.sum())
    return dict(method='independent nearest Moller-Trumbore rays against all participating captured triangles',
        fixed_grid_side=GRID_SIDE, fixed_grid_samples=GRID_SIDE ** 2, deduplicated_samples=len(xs),
        complete_source_triangle_denominator=len(triangles), participating_source_triangle_denominator=denominator,
        ray_triangle_pairs=len(xs) * denominator, maximum_simultaneous_rays=OLD.RAY_CHUNK,
        checked_foreground_samples=int(foreground.sum()), checked_background_samples=int((~foreground).sum()),
        boundary_or_depth_tie_samples=int(ambiguous.sum()), all_image_pixels_checked_for_nearest_surface=False, samples=rows)


def centroid_checks(frame, capture, triangles, object_ids, offsets, participating, source_index, selected, object_mask):
    pose = frame['pose']
    view = np.asarray(pose['view_matrix'], dtype=np.float64)
    projection = np.asarray(pose['projection_matrix'], dtype=np.float64)
    inverse = np.linalg.inv(view)
    centroids = triangles[offsets[source_index] + np.asarray(selected)].mean(axis=1)
    camera = centroids @ view[:3, :3].T + view[:3, 3]
    ndc = camera @ projection[:3, :3].T + projection[:3, 3]
    in_scope = np.all(np.abs(ndc[:, :2]) <= 1, axis=1) & (-camera[:, 2] >= pose['near']) & (-camera[:, 2] <= pose['far'])
    origins = centroids + (-camera[:, 2, None]) * inverse[:3, 2]
    depths, winners, ambiguous = participating_rays(origins, -inverse[:3, 2], triangles,
                                                   participating, pose['near'], pose['far'])
    target_participates = bool(object_mask[source_index])
    blocked = target_participates & in_scope & (winners >= 0) & (depths < -camera[:, 2] - DEPTH_ALLOWANCE_M)
    statuses, rows = Counter(), []
    for index, local in enumerate(selected):
        face = int(winners[index])
        owner = int(object_ids[face]) if face >= 0 else -1
        if not in_scope[index]:
            status = 'outside_image_scope'
        elif not target_participates:
            status = 'selected_region_not_displayed'
        elif blocked[index]:
            status = 'occluded_by_participating_surface'
        else:
            status = 'no_nearer_participating_surface'
        statuses[status] += 1
        rows.append(dict(selected_source_triangle_index=local, centroid_world_m=centroids[index].tolist(),
            centroid_camera_depth_m=float(-camera[index, 2]), inside_image_scope=bool(in_scope[index]),
            selected_geometry_exists=True, selected_object_participates=target_participates, classification=status,
            nearest_global_source_triangle=face, nearest_object_index=owner,
            nearest_object_name=capture['meshes'][owner]['name'] if owner >= 0 else None,
            nearest_local_source_triangle=int(face - offsets[owner]) if owner >= 0 else -1,
            nearest_camera_depth_m=float(depths[index]) if face >= 0 else None,
            centroid_occluded=bool(blocked[index]), boundary_or_depth_tie=bool(ambiguous[index])))
    return dict(centroid_sample_count=len(selected), status_counts=dict(statuses),
        occluded_centroid_samples=int(blocked.sum()),
        occluder_sample_counts=dict(Counter(row['nearest_object_name'] for row in rows if row['centroid_occluded'])),
        participating_source_triangle_denominator=int(participating.sum()),
        centroid_ray_triangle_pairs=len(selected) * int(participating.sum()),
        centroid_visibility_scope='one fixed interior centroid of every selected source triangle', centroid_samples=rows)


def check_frame(frame, full, capture, triangles, object_ids, offsets, source_index, selected, vertices, scope, audit):
    png = audit.file(frame['image_path'], frame['image_sha256'])
    raw = audit.file(frame['arrays_path'], frame['arrays_sha256'])
    with np.load(BytesIO(raw), allow_pickle=False) as saved:
        arrays = {name: saved[name] for name in saved.files}
    with Image.open(BytesIO(png)) as image:
        audit.check(image.format == 'PNG' and image.mode == 'RGB' and image.size == (512, 512)
                    and np.array_equal(np.asarray(image), arrays['color']), 'original_PNG_exact_RGB_array')
    audit.check(set(frame['arrays']) == set(arrays), 'NPZ_exact_declared_array_inventory')
    for name, value in arrays.items():
        audit.check(frame['arrays'][name] == dict(dtype=str(value.dtype), shape=list(value.shape),
            nbytes=value.nbytes, sha256=hashlib.sha256(value.tobytes()).hexdigest()), 'original_buffer_bytes/' + name)
    for name, dtype, shape in (('color', 'uint8', (512, 512, 3)), ('depth', 'float64', (512, 512)),
        ('owners', 'int32', (512, 512)), ('triangle_ids', 'int32', (512, 512)), ('patch_owners', 'int32', (512, 512))):
        audit.check(arrays[name].dtype == np.dtype(dtype) and arrays[name].shape == shape, 'buffer_dtype_shape/' + name)
    audit.check(len(png) == frame['PNG_bytes'] and len(raw) == frame['compressed_array_file_bytes']
                and frame['array_payload_bytes'] == sum(value.nbytes for value in arrays.values()), 'original_encoded_and_raw_frame_sizes')
    audit.check(np.array_equal(arrays['face_patch_offsets'], offsets)
                and np.array_equal(arrays['face_patch_ids'], np.full(len(triangles), -1, dtype=np.int32))
                and arrays['patch_roi_ids'].tolist() == [], 'complete_source_triangle_offsets_empty_rectangular_patch_map')
    ordered = [(tuple(tuple(Fraction(value) for value in point) for point in mesh['vertices']),
                tuple(tuple(face) for face in mesh['faces'])) for mesh in capture['meshes']]
    pixels = SAVED.PIXELS
    mapping = fingerprint(dict(version=pixels.PATCH_SCHEMA, roi_ids=(), ordered_geometry=ordered,
        face_patch_ids=[[-1] * len(mesh['faces']) for mesh in capture['meshes']]))
    owner_mapping = fingerprint((pixels.OWNER_SCHEMA, pixels.TRIANGLE_SCOPE, mapping, offsets.tolist()))
    for name, expected in (('owner_schema', pixels.OWNER_SCHEMA), ('triangle_id_scope', pixels.TRIANGLE_SCOPE),
        ('patch_mapping_version', pixels.PATCH_SCHEMA), ('patch_mapping_identity', mapping), ('owner_mapping_identity', owner_mapping)):
        audit.check(frame[name] == arrays[name].item() == expected, 'original_owner_mapping_preimage/' + name)
    binding = full['binding']
    audit.check(frame['host_binding_sha256'] == binding['binding_sha256']
                and frame['source_revision'] == binding['scene_revision']
                and frame['scene_identity'] == binding['geometry_identity']
                and frame['candidate_identity'] == binding['camera_identity'], 'frame_current_geometry_camera_binding')
    audit.check(frame['pose'] == next(pose for pose in binding['camera_specification']['views'] if pose['name'] == frame['view_name']),
                'frame_exact_published_camera_pose')
    mask = np.asarray(scope['participation_mask'], dtype=bool)
    scope_identity = fingerprint(scope)
    audit.check(frame['display_identity'] == arrays['display_identity'].item() == scope['identity']
                and frame['image_scope'] == scope
                and frame['image_scope_identity'] == arrays['image_scope_identity'].item() == scope_identity,
                'frame_NPZ_exact_current_display_and_image_scope_identity')
    audit.check(arrays['display_object_mask'].dtype == np.dtype('bool')
                and np.array_equal(arrays['display_object_mask'], mask), 'NPZ_exact_fresh_visible_get_participation_mask')
    frame_binding = (frame['scene_identity'], frame['candidate_identity'], scope['identity'], scope_identity, tuple(mask.tolist()))
    preimage = (frame_binding, pixels.OWNER_SCHEMA, owner_mapping, frame['view_name'], 1, frame['image_sha256'])
    audit.check(frame['frame_identity'] == fingerprint(preimage)
                and frame['image_ref'] == 'source-region-image:' + fingerprint((full['region_ref']['region_id'],
                    frame['frame_identity'], frame['image_sha256'])), 'display_bound_frame_and_region_image_identity_preimages')
    audit.check(frame['all_object_count'] == len(capture['meshes']) and frame['all_triangle_count'] == len(triangles),
                'frame_retains_complete_geometry_object_and_triangle_denominators')
    owners, ids, depth = arrays['owners'], arrays['triangle_ids'], arrays['depth']
    foreground = owners >= 0
    audit.check(np.all(owners >= -1) and np.all(owners < len(mask)) and np.all(ids >= -1)
                and np.all(ids < len(triangles)) and np.array_equal(ids >= 0, foreground), 'all_image_source_owner_ranges')
    audit.check(np.all(ids[foreground] >= offsets[owners[foreground]])
                and np.all(ids[foreground] < offsets[owners[foreground] + 1])
                and np.all(mask[owners[foreground]]) and np.all(arrays['patch_owners'] == -1),
                'every_foreground_global_source_triangle_object_and_display_membership')
    audit.check(np.all(np.isposinf(depth[~foreground]))
                and np.all(np.isfinite(depth[foreground]) & (depth[foreground] > 0))
                and np.all(arrays['color'][~foreground] == [18, 22, 30]), 'background_RGB_infinite_depth_positive_foreground')
    selected_points = np.asarray(capture['meshes'][source_index]['vertices'], dtype=np.float64)[vertices]
    camera = OLD.camera_checks(frame['pose'], selected_points, capture, audit)
    pixel_review = OLD.claimed_pixel_checks(frame, arrays, triangles, audit)
    pixel_review['nearest_surface_scope'] = 'separate fixed 16 by 16 grid and all 748 selected-face centroid rays'
    participating = mask[object_ids]
    sampled = grid_checks(frame, arrays, triangles, object_ids, offsets, participating, audit)
    centroid = centroid_checks(frame, capture, triangles, object_ids, offsets, participating, source_index, selected, mask)
    counts = np.bincount(ids[foreground], minlength=len(triangles))
    selected_counts = {str(index): int(counts[offsets[source_index] + index]) for index in selected}
    visible = [index for index in selected if selected_counts[str(index)] > 0]
    unseen = [index for index in selected if selected_counts[str(index)] == 0]
    ys, xs = np.nonzero(np.isin(ids, offsets[source_index] + np.asarray(selected)))
    bounds = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())] if len(xs) else None
    visibility = full['facts']['visibility']
    audit.check(visibility['visible_source_triangle_indices'] == visible
                and visibility['unseen_source_triangle_indices'] == unseen
                and visibility['selected_surface_pixels'] == len(xs) and visibility['visible_pixel_bounds'] == bounds
                and visibility['image_ref'] == frame['image_ref'] and visibility['frame_identity'] == frame['frame_identity']
                and visibility['image_scope'] == scope and visibility['selected_source_triangle_count'] == len(selected)
                and visibility['selected_object_participates'] == bool(mask[source_index]), 'published_selected_visibility_exact_saved_source_pixels')
    audit.check(visibility['complete_witness'] is None
                and visibility['visibility_scope'] == 'actual_frame_source_triangle_samples'
                and 'complete_surface_visibility' in visibility['unknown'], 'complete_surface_visibility_remains_unknown')
    reason = None if len(xs) else ('selected_region_displayed_without_pixels' if mask[source_index] else 'selected_region_not_displayed')
    audit.check(visibility['status'] == ('observed_samples' if len(xs) else 'unknown')
                and visibility.get('reason') == reason
                and full['status'] == ('complete' if len(xs) else 'partial')
                and full['observation_status'] == ('locally_observed' if len(xs) else 'evidence_insufficient'),
                'direct_nonzero_or_insufficient_image_feedback')
    return dict(frame_identity=frame['frame_identity'], image_ref=frame['image_ref'], image_path=frame['image_path'],
        image_sha256=frame['image_sha256'], arrays_sha256=frame['arrays_sha256'], display_identity=scope['identity'],
        image_scope_identity=scope_identity, participation_mask=mask.tolist(), camera_fit=camera,
        full_image_source_pixel_review=pixel_review, sampled_nearest_scene_review=sampled, selected_centroid_review=centroid,
        selected_region_image_evidence='pass' if len(xs) else 'unknown', selected_region_image_reason=reason,
        selected_surface_pixels=len(xs), selected_triangle_pixel_counts=selected_counts,
        visible_source_triangle_indices=visible, unseen_source_triangle_indices=unseen,
        complete_selected_surface_visibility='unknown',
        visible_object_pixel_counts={mesh['name']: int(np.count_nonzero(owners == index)) for index, mesh in enumerate(capture['meshes'])})


def review(full, capture, snapshot, audit):
    started = time.perf_counter()
    audit.check(full['read_only'] is True and full['execution_authority'] is False, 'source_region_read_only')
    source = OLD.snapshot_checks(snapshot, capture, full['binding'], audit)
    scope = display_checks(snapshot, capture, full['binding'], audit)
    source_index, selected, vertices = OLD.region_checks(full, capture, audit)
    audit.check(len(selected) == 748 and len(vertices) == 410, 'fixed_ARM_748_triangles_410_vertices')
    previous = audit.read(FIXED_PUBLIC, FIXED_PUBLIC_SHA)
    for key in ('object_name', 'index_domain', 'source_triangle_indices', 'source_vertex_indices',
                'triangles_source_vertices', 'vertices_world_m', 'bbox_min_world_m', 'bbox_max_world_m'):
        audit.check(full['facts']['region'][key] == previous['facts']['region'][key],
                    'fixed_prior_actual_selected_source_region/' + key)
    audit.check(len(full['frames']) == 1
                and full['frames'][0]['pose'] == previous['frames'][0]['pose'],
                'fixed_prior_actual_SCENE_camera_exact_unchanged')
    triangles, object_ids, offsets = OLD.scene_arrays(capture)
    audit.check(len(triangles) == 53276, 'complete_original_53276_source_triangles')
    frames = [check_frame(frame, full, capture, triangles, object_ids, offsets, source_index,
                          selected, vertices, scope, audit) for frame in full['frames']]
    audit.check(len(frames) == 1, 'one_actual_SCENE_source_region_frame')
    return dict(schema=SCHEMA, passed_checked_scope=True, saved_image_integrity='pass',
        selected_region_image_evidence=frames[0]['selected_region_image_evidence'],
        selected_region_image_reason=frames[0]['selected_region_image_reason'],
        status=full['status'], observation_status=full['observation_status'], image_scope=scope,
        selected_source_triangle_count=len(selected), selected_source_vertex_count=len(vertices),
        source_object_index=source_index, source_object_name=capture['meshes'][source_index]['name'],
        fresh_source_capture_comparisons=source, all_scene_triangle_count=len(triangles), frames=frames,
        independent_check_elapsed_seconds=time.perf_counter() - started,
        precision=dict(barycentric_allowance=OLD.BARYCENTRIC_ALLOWANCE, camera_depth_allowance_m=DEPTH_ALLOWANCE_M,
                       snapshot_world_coordinate_allowance_m=OLD.WORLD_ALLOWANCE_M),
        nearest_ray_policy=dict(grid_side=GRID_SIDE, selected_centroids='all 748 selected source triangle centroids',
            participation='fresh captured active view layer visible_get', ray_chunk=OLD.RAY_CHUNK),
        full_foreground_nearest_surface_claim=False, product_imports=0,
        author_association='Independent saved-evidence checker reuses sealed prior byte readers and mathematical ray primitives.',
        new_operations=dict(Blender=0, raster=0, model=0, paid=0), checks=audit.checks, input_pins=list(audit.pins.values()))


def public_checks(request, response, full, session, audit):
    audit.check(request['id'] == response['id'] and response['result']['isError'] is False
                and request['params']['name'] == 'human_eye_scene_observe'
                and request['params']['arguments']['query']['mode'] == 'source_region', 'original_public_source_region_entry_and_success')
    arguments = request['params']['arguments']
    texts = [json.loads(block['text']) for block in response['result']['content'] if block['type'] == 'text']
    images = [block for block in response['result']['content'] if block['type'] == 'image']
    audit.check(len(texts) == 1 and texts[0]['region_ref'] == full['region_ref'], 'public_text_exact_current_region_ref')
    public = texts[0]
    for key in ('status', 'observation_status', 'task_result', 'read_only', 'execution_authority'):
        audit.check(public[key] == full[key], 'public_same_producer_' + key)
    if arguments.get('response_detail') == 'full':
        audit.check(public['binding'] == full['binding'] and public['facts'] == full['facts']
                    and public['frames'] == full['frames'], 'full_exact_display_binding_visibility_and_frames')
    else:
        binding = {key: value for key, value in full['binding'].items() if key != 'camera_specification'}
        audit.check(public['schema'] == 'source-region-brief-v1' and public['binding'] == binding
                    and public['region'] == full['facts']['region'] and public['visibility'] == full['facts']['visibility']
                    and public['measurement_scope'] == full['task_result']['measurement_scope'], 'brief_complete_display_scope_visibility_measurement')
        audit.check(len(public['images']) == len(full['frames']), 'brief_native_image_reference_count')
        for index, (image, frame) in enumerate(zip(public['images'], full['frames'], strict=True), 1):
            expected = {key: frame[key] for key in ('image_ref', 'view_name', 'frame_identity', 'image_sha256',
                'camera_identity', 'host_binding_sha256', 'display_identity', 'image_scope_identity') if key in frame}
            audit.check(image == dict(expected, image_block_index=index), 'brief_exact_native_display_bound_frame_reference')
        reason = full['facts']['visibility'].get('reason')
        if reason is not None:
            audit.check(dict(scope='image_evidence', reason=reason) in public['unknowns'], 'brief_direct_image_insufficiency_reason')
    audit.check(len(images) == len(full['frames']) == int(arguments['include_image']), 'public_native_image_count')
    for image, frame in zip(images, full['frames'], strict=True):
        audit.check(image['mimeType'] == 'image/png' and base64.b64decode(image['data'], validate=True)
                    == audit.file(frame['image_path'], frame['image_sha256'], session), 'public_native_PNG_exact_saved_bytes')
    return arguments.get('response_detail', 'brief')


def check_session(session, run_binding, snapshot, call_index=1, audit=None):
    session = Path(session).resolve()
    audit = Audit() if audit is None else audit
    installed = audit.read(run_binding)
    audit.check(len(installed['source_manifest']) == 143, 'candidate_143_runtime_sources')
    calls = [json.loads(line) for line in audit.file(session / 'PUBLIC_REQUESTS.jsonl').splitlines() if line.strip()]
    call = calls[call_index - 1]
    full = audit.read(call['producer_archive']['path'], call['producer_archive']['sha256'], session)
    request = audit.read(call['request_path'], call['request_sha256'], session)
    response = audit.read(call['response_path'], call['response_sha256'], session)
    audit.check(request == audit.read(call['actual_TX_path'], call['actual_TX_sha256'], session)
                and response == audit.read(call['actual_RX_path'], call['actual_RX_sha256'], session), 'original_public_request_response_actual_stdio_bytes')
    audit.check(full['binding']['runtime_source_sha256'] == installed['source_sha256']
                and full['binding']['source_status'] == 'loaded_generation'
                and full['binding']['disk_status'] == 'disk_not_checked'
                and full['binding']['source_check_scope'] == 'bound_generation_identity', 'new_R0_runtime_source_attestation')
    detail = public_checks(request, response, full, session, audit)
    captures, commands = SAVED.decode_captures(session, installed, audit)
    capture = current_capture(captures, full['binding'], audit)
    result = review(full, capture, audit.read(snapshot), audit)
    result.update(session=str(session), call_index=call_index, response_detail=detail,
                  original_wire_commands=commands, original_public_delivery_checked=True)
    return result


def check_saved(full_path, capture_path, snapshot_path):
    audit = Audit()
    full, document, snapshot = [audit.read(path) for path in (full_path, capture_path, snapshot_path)]
    result = review(full, document.get('capture', document), snapshot, audit)
    result['original_public_delivery_checked'] = False
    return result


def failure(error, audit=None):
    return dict(schema=SCHEMA, passed_checked_scope=False, error_type=type(error).__name__, error=str(error),
        traceback=traceback.format_exc(), checks=[] if audit is None else audit.checks,
        input_pins=[] if audit is None else list(audit.pins.values()),
        new_operations=dict(Blender=0, raster=0, model=0, paid=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', type=Path)
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--run-binding', type=Path)
    parser.add_argument('--call-index', type=int, default=1)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    audit = Audit()
    try:
        result = (check_session(args.session, args.run_binding, args.snapshot, args.call_index, audit)
                  if args.session is not None else check_saved(args.full, args.capture, args.snapshot))
    except Exception as error:
        result = failure(error, audit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps(dict(passed_checked_scope=result['passed_checked_scope'], output=str(args.output.resolve()),
        error=result.get('error'), selected_region_image_evidence=result.get('selected_region_image_evidence'))))
    raise SystemExit(0 if result['passed_checked_scope'] else 1)


if __name__ == '__main__':
    main()
