"""Discover geometric task regions and collect same-capture local witnesses."""

from __future__ import annotations

import copy
from fractions import Fraction
import hashlib
import json
import math
import time
from pathlib import Path

from .active_observation import (
    ActiveObservationSession, CoverageState, build_index_from_parsed, cross, dot,
    fingerprint, geometry, prepare_coverage_index, subtract,
)
from .active_observation_images import ActiveObservationImages, _meshes_from_objects
from .blender_host import _observation_affine_interval, _observation_target_cameras
from .query_policy import validate_region_task


def region_matches(region, conditions):
    """Compare exact area and oriented unit-z inequalities without square roots."""
    minimum = Fraction(str(conditions['area_min_m2']))
    maximum = Fraction(str(conditions['area_max_m2']))
    threshold = Fraction(str(conditions['normal_z_min']))
    first, second, _, fourth = region.vertices
    normal = cross(subtract(second, first), subtract(fourth, first))
    squared = dot(normal, normal)
    if not minimum * minimum <= squared <= maximum * maximum:
        return False
    z = normal[2]
    if threshold >= 0:
        return z >= 0 and z * z >= threshold * threshold * squared
    return z >= 0 or z * z <= threshold * threshold * squared


def _ordered_geometry_sha256(mesh):
    raw = json.dumps({'vertices': mesh['vertices'], 'faces': mesh['faces']},
                     sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('utf8')
    return hashlib.sha256(raw).hexdigest()


def _source(region, capture, binding):
    host = binding['objects'][region.object_index]
    return dict(document_epoch=binding['document_epoch'], host_id=host['host_id'],
        instance_id=host['instance_id'], object_index=region.object_index,
        source_triangle_indices=list(region.triangle_indices),
        ordered_geometry_sha256=_ordered_geometry_sha256(capture['meshes'][region.object_index]),
        parent_binding_sha256=binding['binding_sha256'],
        parent_source_binding_sha256=binding['source_binding_sha256'],
        scene_revision=binding['scene_revision'], capture_state=copy.deepcopy(binding['capture_state']))


def _local_binding(parent, source, cameras, scene_identity):
    binding = {key: copy.deepcopy(parent[key]) for key in (
        'scene_revision', 'document_epoch', 'capture_state', 'unit', 'coordinate_frame', 'source', 'objects')}
    binding.update(schema='active-observation-region-source-v1', capture_scope='same_capture_region_view',
        parent_binding_sha256=parent['binding_sha256'],
        parent_source_binding_sha256=parent['source_binding_sha256'], region_source=copy.deepcopy(source),
        camera_policy=dict(scope='region_fitted_viewport_full_scene_depth',
            order=list(cameras['directions']), size_px=[512, 512]))
    binding['source_binding_sha256'] = fingerprint(binding)
    binding['camera_specification'] = copy.deepcopy(cameras)
    binding['geometry_identity'] = scene_identity
    binding['camera_identity'] = fingerprint([
        {key: pose[key] for key in ('name', 'direction_rational', 'view_matrix', 'projection_matrix', 'size_px')}
        for pose in cameras['views']])
    binding['binding_sha256'] = fingerprint(binding)
    return binding


def _local_patch_scope(objects, region):
    rows = []
    for index, item in enumerate(objects):
        supported = list(region.triangle_indices) if index == region.object_index else []
        support_set = set(supported)
        rows.append(dict(object_index=index, source_triangle_count=len(item[1]),
            supported_triangle_indices=supported, supported_triangle_count=len(supported),
            occluder_only_triangle_indices=[face for face in range(len(item[1])) if face not in support_set],
            coverage_role='task_region' if supported else 'occluder_only'))
    return dict(schema='active-region-task-patch-support-v1',
        triangle_index_scope='zero-based source triangles within each object',
        all_triangles_participate_in_occlusion=True, objects=rows,
        regions=[dict(roi_id=region.roi_id, object_index=region.object_index,
                      triangle_indices=list(region.triangle_indices))])


def _outward(value, direction):
    return math.nextafter(value, direction)


def _subtract_interval(first, second):
    return (_outward(first[0] - second[1], -math.inf), _outward(first[1] - second[0], math.inf))


def _multiply_interval(first, second):
    values = [a * b for a in first for b in second]
    return (_outward(min(values), -math.inf), _outward(max(values), math.inf))


def _float_upper(value):
    result = float(value)
    return _outward(result, math.inf) if Fraction(result) < value else result


def _screen_intervals(point, pose):
    view, projection = pose['view_matrix'], pose['projection_matrix']
    world = [float(value) for value in point]
    camera = [_observation_affine_interval([world, world], row[:3], row[3]) for row in view[:3]]
    if any(row is None for row in camera) or camera[2][1] >= 0:
        return None
    bounds = [[row[0] for row in camera], [row[1] for row in camera]]
    ndc = [_observation_affine_interval(bounds, row[:3], row[3]) for row in projection[:3]]
    # Avoid polygon-clipping interpolation entirely. Its uncertainty returns to
    # the existing real observation path instead of receiving a pixel bound.
    if any(row is None or row[0] <= -1 or row[1] >= 1 for row in ndc):
        return None
    x = _subtract_interval(ndc[0], (-1., -1.))
    y = _subtract_interval((1., 1.), ndc[1])
    return tuple(_multiply_interval(_multiply_interval(axis, (511., 511.)), (.5, .5)) for axis in (x, y))


def pixel_center_upper_bound(region, objects, pose):
    """Enclose accepted half-integer samples, including floating barycentrics.

    Published binary64 matrices are the inputs to both the exact classifier
    and the two-stage raster transform. The host affine interval encloses each
    dot ordering and gradual underflow. Every source triangle is checked.
    """
    unknown = dict(roi_id=region.roi_id, status='unknown', upper_bound=None)
    try:
        if (pose.get('projection') != 'orthographic' or pose.get('size_px') != [512, 512]
                or any(matrix[3] != [0., 0., 0., 1.] for matrix in
                       (pose['view_matrix'], pose['projection_matrix']))):
            return dict(unknown, reason='unsupported_pixel_projection')
        source = objects[region.object_index]
        vertices = sorted({index for face in region.triangle_indices for index in source[1][face]})
        screens = {index: _screen_intervals(source[0][index], pose) for index in vertices}
        if any(value is None for value in screens.values()):
            return dict(unknown, reason='clipping_or_transform_bound_unknown')
        unit = Fraction(1, 2**53)
        gamma = 32 * unit / (1 - 32 * unit)
        gamma4 = 4 * unit / (1 - 4 * unit)
        underflow = 32 * Fraction(math.ulp(0.))
        lower, upper = [math.inf, math.inf], [-math.inf, -math.inf]
        certificates = []
        for face_index in region.triangle_indices:
            points = [screens[index] for index in source[1][face_index]]
            a, b, c = points
            area = _subtract_interval(
                _multiply_interval(_subtract_interval(b[0], a[0]), _subtract_interval(c[1], a[1])),
                _multiply_interval(_subtract_interval(b[1], a[1]), _subtract_interval(c[0], a[0])))
            area_lower = min(abs(value) for value in area) if area[0] * area[1] > 0 else 0
            if area_lower <= 2. ** -31:
                return dict(unknown, reason='triangle_area_bound_unresolved')
            low = [min(point[axis][0] for point in points) for axis in (0, 1)]
            high = [max(point[axis][1] for point in points) for axis in (0, 1)]
            span = [_outward(high[axis] - low[axis], math.inf) for axis in (0, 1)]
            # The raster only visits floor(min)..ceil(max), followed by +.5.
            # Thus each numerator's coordinate differences are bounded by
            # span+1.5. Using span+2 also covers endpoint-rounding intervals.
            sx, sy, minimum_area = Fraction(span[0]), Fraction(span[1]), Fraction(area_lower)
            numerator_max = 2 * (sx + 2) * (sy + 2)
            area_max = 2 * sx * sy
            area_error = gamma * area_max + underflow
            numerator_error = gamma * numerator_max + underflow
            quotient_max = (numerator_max + numerator_error) / minimum_area * (1 + 2 * unit) + underflow
            error = (numerator_error / minimum_area
                + (numerator_max / minimum_area) * (area_error / minimum_area)
                + 4 * unit * quotient_max + underflow)
            # w2 is evaluated as two further subtractions, whereas its exact
            # counterpart is 1-lambda0-lambda1. This bounds all three lambdas.
            # Exact rational bound arithmetic prevents the bound calculation
            # itself from rounding inward. Only its final publication is float.
            epsilon = _float_upper(Fraction(1e-10) + 2 * error + gamma4 * (1 + 2 * quotient_max) + underflow)
            if not math.isfinite(epsilon) or epsilon >= .01:
                return dict(unknown, reason='barycentric_conditioning_unresolved')
            # All accepted exact lambdas are >=-epsilon and sum to one.
            # At most two negative terms extend either axis past its extrema.
            for axis in (0, 1):
                expansion = _outward(2 * epsilon * span[axis], math.inf)
                lower[axis] = min(lower[axis], _outward(low[axis] - expansion, -math.inf))
                upper[axis] = max(upper[axis], _outward(high[axis] + expansion, math.inf))
            certificates.append(dict(source_triangle_index=face_index, area_interval=list(area),
                area_absolute_lower=area_lower, barycentric_coordinate_error_bound=epsilon - 1e-10,
                accepted_exact_lambda_lower=-epsilon))
        ranges = []
        for low, high in zip(lower, upper):
            first = max(0, math.ceil(_outward(low - .5, -math.inf)))
            last = min(511, math.floor(_outward(high - .5, math.inf)))
            ranges.append([first, last])
        count = math.prod(max(0, last - first + 1) for first, last in ranges)
        return dict(roi_id=region.roi_id, status='bounded', upper_bound=count,
            screen_bounds=[lower, upper], pixel_index_ranges=ranges, source_triangles=certificates,
            method='outward_two_stage_projection_and_barycentric_error',
            threshold_surface_pixels=16, actual_observation=False)
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, ZeroDivisionError):
        return dict(unknown, reason='pixel_bound_numeric_unresolved')


def _task_next_view(session, relevant, skipped=()):
    if not session.state.observed_views:
        return session.state.first_view if relevant else None
    mask = sum(1 << index for index, region in enumerate(session.regions) if region.roi_id in relevant)
    unresolved = mask & ~session.state.covered_mask
    candidates = [(name, (bits & unresolved).bit_count()) for name, bits in session.index.view_masks.items()
                  if name not in session.state.observed_views and name not in skipped and bits & unresolved]
    return max(candidates, key=lambda row: row[1])[0] if candidates else None


def _local_first_view(index, region_id):
    if index.classifications['SCENE'][region_id]['status'] == 'positive_area_occlusion':
        # This private index has only the target region. Its existing mask
        # identifies the directions that can complete the geometric witness.
        return next((name for name in index.view_order if index.view_masks[name]), 'SCENE')
    return 'SCENE'


def _facts(session, binding, scope_id, frames):
    facts = session.short_facts()
    by_view = {frame['view_name']: frame for frame in frames}
    for row in facts['regions']:
        host = binding['objects'][row['object_index']]
        row.update(host_id=host['host_id'], instance_id=host['instance_id'])
    for observation in facts['observations']:
        frame = by_view[observation['view_name']]
        observation.update(scope_id=scope_id, frame_identity=frame['frame_identity'])
        for row in observation['pixel_rows']:
            host = binding['objects'][row['object_index']]
            row.update(host_id=host['host_id'], object_name=host['object_name'])
    return facts


def _witness(scope, region_id, frames_by_id):
    evidence = next(row for row in scope['facts']['region_evidence'] if row['roi_id'] == region_id)
    raw = evidence['complete_witness']
    if raw is None:
        return None
    observation = next(row for row in scope['facts']['observations'] if row['view_name'] == raw['view_name'])
    frame = frames_by_id[observation['frame_identity']]
    return dict(scope_id=scope['scope_id'], view_name=raw['view_name'], frame_identity=frame['frame_identity'],
                image_ref=frame['image_ref'], pixel_row_index=raw['pixel_row_index'])


def _render_scope(session, meshes, binding, scope_id, relevant, output, work, stages,
                  check_budget, construction_callback, include_image):
    from .active_observation_host import _interval
    frames, steps, skipped = [], [], []
    images = None
    if include_image and relevant:
        started = time.perf_counter_ns()
        work['patch_mapping_calls'] += 1
        images = ActiveObservationImages(session, output / binding['binding_sha256'],
                                         _prepared_meshes=(session.objects, meshes), _measure_stages=True)
        stages['patch_mapping_' + scope_id] = _interval(started)
    while images is not None:
        name = _task_next_view(session, relevant, {row['view_name'] for row in skipped})
        if name is None:
            break
        if scope_id == 'global' and frames:
            started = time.perf_counter_ns()
            pose = next(item for item in session.cameras['views'] if item['name'] == name)
            covered = set(session.summary()['covered_roi_ids'])
            bounds = [pixel_center_upper_bound(region, session.objects, pose) for region in session.regions
                      if region.roi_id in relevant and region.roi_id not in covered
                      and session.index.classifications[name][region.roi_id]['complete']]
            work['pixel_bound_region_calls'] += len(bounds)
            stages['pixel_bounds_' + name] = _interval(started)
            if bounds and all(row['status'] == 'bounded' and row['upper_bound'] < 16 for row in bounds):
                skipped.append(dict(view_name=name, reason='pixel_upper_bound_below_readability',
                    regions=bounds, actual_observation=False,
                    geometric_non_candidates=[dict(roi_id=region.roi_id,
                        classification=session.index.classifications[name][region.roi_id]['status'])
                        for region in session.regions if region.roi_id in relevant and region.roi_id not in covered
                        and not session.index.classifications[name][region.roi_id]['complete']]))
                work['global_views_skipped'] += 1
                continue
        if check_budget is not None:
            check_budget('active_observation_before_raster')
        if construction_callback is not None:
            construction_callback(name)
        work['raster_attempts'] += 1
        started = time.perf_counter_ns()
        frame = images.render_view(name)
        work['raster_completed'] += 1
        for destination, key in (('PNG_bytes', 'PNG_bytes'), ('NPZ_bytes', 'compressed_array_file_bytes'),
                                 ('array_payload_bytes', 'array_payload_bytes')):
            work[destination] += frame[key]
        frame.update(scope_id=scope_id, host_binding_sha256=binding['binding_sha256'],
                     source_revision=binding['scene_revision'], camera_identity=binding['camera_identity'])
        reference = (binding['binding_sha256'], name, frame['image_sha256'], frame['patch_mapping_identity'],
                     frame['owner_schema'], frame['owner_mapping_identity'], frame['frame_identity'])
        frame['image_ref'] = 'active-host-image:' + fingerprint(reference)
        stages['render_and_publish_' + scope_id + '_' + name] = _interval(started)
        started = time.perf_counter_ns()
        feedback = images.observe_frame(frame)
        stages['feedback_' + scope_id + '_' + name] = _interval(started)
        work['local_verified_images'] += 1
        saved = {key: value for key, value in frame.items() if key != 'buffers'}
        saved['feedback_stages'] = feedback['stages']
        frames.append(saved)
        steps.append(dict(scope_id=scope_id, view_name=name, frame_identity=frame['frame_identity'],
                          update=feedback['update'], summary=feedback['summary']))
    facts = _facts(session, binding, scope_id, frames)
    return dict(scope_id=scope_id, binding=binding, facts=facts, skipped_views=skipped,
                frame_refs=[frame['frame_identity'] for frame in frames], steps=steps), frames


def observe_region_task(capture, output_directory, conditions, *, construction_callback=None,
                        check_budget=None, include_image=True, geometry_ids_callback=None,
                        prepare_global_index=None):
    """Run finite global and region-fitted views over one immutable capture."""
    from .active_observation_host import (
        _interval, _location_conventions, _patch_scope_facts, freeze_cameras,
        scene_from_capture, source_binding,
    )
    if type(include_image) is not bool:
        raise ValueError('active_observation_include_image_boolean_required')
    conditions = validate_region_task(conditions)
    work = dict(mapping_calls=0, geometry_parse_calls=0, mesh_conversions=0, partition_calls=0,
                camera_calls=0, local_camera_calls=0, prepare_calls=0, index_calls=0,
                patch_mapping_calls=0, raster_attempts=0, raster_completed=0,
                local_verified_images=0, PNG_bytes=0, NPZ_bytes=0, array_payload_bytes=0,
                pixel_bound_region_calls=0, global_views_skipped=0, global_index_cache_hit=False)
    stages = {}
    try:
        if check_budget is not None:
            check_budget('active_observation_before_prepare')
        started = time.perf_counter_ns()
        initial_binding = source_binding(capture)
        if 'observation_target' in initial_binding:
            raise ValueError('region_task_requires_complete_scene_capture')
        scene = scene_from_capture(capture)
        work['mapping_calls'] += 1
        stages['capture_mapping'] = _interval(started)
        started = time.perf_counter_ns()
        objects, triangles, scene_identity = geometry(scene)
        work['geometry_parse_calls'] += 1
        stages['geometry'] = _interval(started)
        started = time.perf_counter_ns()
        meshes = _meshes_from_objects(objects)
        work['mesh_conversions'] += 1
        if geometry_ids_callback is not None:
            geometry_ids_callback(tuple(mesh.object_id for mesh in meshes))
        stages['mesh_arrays'] = _interval(started)
        work.update(capture_object_count=len(objects), captured_vertex_count=sum(len(item[0]) for item in objects),
                    captured_triangle_count=len(triangles), geometry_array_payload_bytes=sum(
                        mesh.vertices.nbytes + mesh.faces.nbytes + mesh.edges.nbytes for mesh in meshes))
        started = time.perf_counter_ns()
        cameras = freeze_cameras(meshes)
        work['camera_calls'] += 1
        stages['cameras'] = _interval(started)
        started = time.perf_counter_ns()

        def build_global():
            work['prepare_calls'] += 1
            work['partition_calls'] += 1
            work['index_calls'] += 1
            index, timing = prepare_coverage_index(objects, triangles, scene_identity, cameras, diagnostics=True)
            stages.update(partition=timing['discovery'], index_global=timing['coverage'])
            if check_budget is not None:
                check_budget('active_observation_after_global_index')
            return index

        if prepare_global_index is None:
            index, reused = build_global(), False
        else:
            index, reused = prepare_global_index(build_global)
        work['global_index_cache_hit'] = reused
        session = ActiveObservationSession(objects, triangles, cameras, index, CoverageState(index))
        stages['prepare'] = _interval(started)
        binding = source_binding(capture, cameras, geometry_identity=scene_identity)
        if reused and (index.scene_identity, index.candidate_identity) != (scene_identity, binding['camera_identity']):
            raise ValueError('active_observation_prepared_index_binding_mismatch')
        started = time.perf_counter_ns()
        eligible = [region for region in session.regions if region_matches(region, conditions)]
        eligible.sort(key=lambda region: (binding['objects'][region.object_index]['host_id'],
                                         binding['objects'][region.object_index]['instance_id'], region.triangle_indices))
        sources = {region.roi_id: _source(region, capture, binding) for region in eligible}
        stages['task_filter_and_source'] = _interval(started)
        output = Path(output_directory).resolve()
        global_scope, constructed = _render_scope(session, meshes, binding, 'global',
            {region.roi_id for region in eligible}, output, work, stages,
            check_budget, construction_callback, include_image)
        global_scope['facts']['scope'] = _patch_scope_facts(session, binding)
        global_scope['facts']['location_conventions'] = _location_conventions(cameras)
        scopes = [global_scope]
        by_identity = {frame['frame_identity']: frame for frame in constructed}
        global_regions = {row['roi_id']: row for row in global_scope['facts']['regions']}
        world_bounds = [[mesh.vertices.min(axis=0).tolist(), mesh.vertices.max(axis=0).tolist()] for mesh in meshes]
        rows = []
        for region in eligible:
            witness = _witness(global_scope, region.roi_id, by_identity)
            scope = global_scope
            candidate = any(pose[region.roi_id]['complete'] for pose in session.index.classifications.values())
            if include_image and witness is None and candidate:
                if check_budget is not None:
                    check_budget('active_observation_before_local_prepare')
                started = time.perf_counter_ns()
                local_cameras = _observation_target_cameras(
                    [[float(value) for value in point] for point in region.vertices], world_bounds)
                work['local_camera_calls'] += 1
                scope_id = 'local_' + fingerprint(sources[region.roi_id])[:24]
                stages['cameras_' + scope_id] = _interval(started)
                started = time.perf_counter_ns()
                local_index = build_index_from_parsed(objects, triangles, scene_identity, (region,), local_cameras)
                work['index_calls'] += 1
                state = CoverageState(local_index, first_view=_local_first_view(local_index, region.roi_id))
                local_session = ActiveObservationSession(objects, triangles, local_cameras, local_index,
                                                         state)
                stages['index_' + scope_id] = _interval(started)
                local_binding = _local_binding(binding, sources[region.roi_id], local_cameras, scene_identity)
                scope, frames = _render_scope(local_session, meshes, local_binding, scope_id, {region.roi_id},
                    output, work, stages, check_budget, construction_callback, include_image)
                scope['facts']['scope'] = dict(kind='same_capture_region', roi_id=region.roi_id,
                    all_objects_participate_in_occlusion=True, capture_object_count=len(objects),
                    source_triangle_count=len(triangles), source=sources[region.roi_id],
                    patch_support=_local_patch_scope(objects, region))
                scope['facts']['location_conventions'] = _location_conventions(local_cameras)
                scopes.append(scope)
                constructed.extend(frames)
                by_identity.update((frame['frame_identity'], frame) for frame in frames)
                witness = _witness(scope, region.roi_id, by_identity)
            row = copy.deepcopy(global_regions[region.roi_id])
            evidence = next(item for item in scope['facts']['region_evidence'] if item['roi_id'] == region.roi_id)
            if witness is not None:
                row.update(status='covered', reason='observed_readable')
            else:
                row.update(status='unknown', reason=evidence['unobserved_reason'] or row['reason'])
            row.update(source_triangle_indices=list(region.triangle_indices), source=sources[region.roi_id],
                       complete_witness=witness, view_reasons=copy.deepcopy(evidence['view_reasons']))
            rows.append(row)
        selected = constructed[:1]
        selected_ids = {frame['frame_identity'] for frame in selected}
        for row in rows:
            witness = row['complete_witness']
            if witness is None:
                continue
            identity = witness['frame_identity']
            if identity not in selected_ids and len(selected) < 6:
                selected.append(by_identity[identity])
                selected_ids.add(identity)
            witness['selected_for_delivery'] = identity in selected_ids
        unsupported = sum(item['unsupported_triangle_count'] for item in session.index.patch_scope)
        task = dict(schema='active-region-task-v1', conditions=conditions, rows=rows,
            summary=dict(eligible_region_count=len(rows), observed_region_count=sum(row['status'] == 'covered' for row in rows),
                unknown_region_count=sum(row['status'] == 'unknown' for row in rows),
                supported_region_count=len(session.regions), supported_triangle_count=len(triangles) - unsupported,
                unsupported_triangle_count=unsupported, source_triangle_count=len(triangles),
                selected_image_count=len(selected), constructed_image_count=len(constructed),
                external_consumer_verified=False))
        facts = copy.deepcopy(global_scope['facts'])
        facts['region_task'] = task
        if check_budget is not None:
            check_budget('active_observation_before_result')
        return dict(status='complete' if include_image and rows else 'predicted' if rows else 'unknown',
            result_kind='active_observation', observation_status='region_task_observed' if include_image else 'prediction_only',
            binding=binding, facts=facts, frames=selected, constructed_frames=constructed, scopes=scopes,
            steps=[step for scope in scopes for step in scope['steps']], work=work, stages=stages,
            read_only=True, execution_authority=False,
            image_delivery=dict(local_verified=len(constructed), mcp_content_constructed=0, external_consumer_verified=False))
    except Exception as error:
        error.active_observation_work = copy.deepcopy(work)
        error.active_observation_stages = copy.deepcopy(stages)
        error.active_observation_byte_scope = 'completed frame metadata lower bound on failure'
        raise
