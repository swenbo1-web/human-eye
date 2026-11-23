"""Registered, read-only Blender host-window diagnostics for bound qualification."""

import math
import struct
import time


DIAGNOSTIC_SCHEMA = 'm4-live-bounds-diagnostic-v1'


def interval(started):
    closed = time.perf_counter_ns()
    return {'started_ns': started, 'closed_ns': closed, 'elapsed_ns': closed - started}


def world_point(matrix, point, scale):
    """Use the installed complete capture's original Python operation sequence."""
    return [(sum(matrix[row][col] * point[col] for col in range(3)) + matrix[row][3]) * scale
            for row in range(3)]


def bounds_bits(bounds):
    return [[struct.pack('>d', value).hex() for value in corner] for corner in bounds]


def axes_from_matrix(matrix):
    return [[axis for axis, value in enumerate(row[:3]) if value != 0.0] for row in matrix[:3]]


def local_limits(corners):
    if corners is None or len(corners) != 8:
        return None, 'corner_count_or_RNA_unavailable'
    if not all(math.isfinite(component) for point in corners for component in point):
        return None, 'nonfinite_RNA_corner'
    if all(tuple(point) == (-1.0, -1.0, -1.0) for point in corners):
        return None, 'missing_RNA_corners_negative_one_sentinel'
    low = [min(point[i] for point in corners) for i in range(3)]
    high = [max(point[i] for point in corners) for i in range(3)]
    expected = {(x, y, z) for x in (low[0], high[0]) for y in (low[1], high[1])
                for z in (low[2], high[2])}
    if {tuple(point) for point in corners} != expected:
        return None, 'not_cartesian_RNA_corners'
    return [low, high], None


def direct_bounds(corners, matrix, scale, outward):
    """Try the axis-separable hypothesis without borrowing the truth scan."""
    axes = axes_from_matrix(matrix)
    limits, reason = local_limits(corners)
    if reason is None and outward is None:
        reason = 'installed_outward_interval_unavailable'
    if reason is None and any(len(terms) > 1 for terms in axes):
        reason = 'mixed_world_axis_binary64'
    if reason is not None:
        return None, axes, reason
    lower, upper = world_point(matrix, limits[0], scale), world_point(matrix, limits[1], scale)
    tight = [[], []]
    for i, (a, b) in enumerate(zip(lower, upper)):
        if not math.isfinite(a) or not math.isfinite(b):
            return None, axes, 'nonfinite_direct_endpoints'
        low, high = min(a, b), max(a, b)
        if scale <= 0.5 and (low == 0.0 or high == 0.0):
            # A negative nonzero pre-scale value can round to -0 here.
            # Endpoint signs cannot establish the reduction winner over a mixed zero plateau.
            return None, axes, 'zero_plateau_sign_needs_ordered_world_scan'
        if a == b == 0.0 and math.copysign(1.0, a) != math.copysign(1.0, b):
            return None, axes, 'mixed_signed_zero_endpoints'
        if not outward[0][i] <= low <= high <= outward[1][i]:
            return None, axes, 'direct_bound_outside_installed_outward_interval'
        tight[0].append(low)
        tight[1].append(high)
    return tight, axes, None


def identity_pointer(rna):
    pointer = getattr(rna, 'as_pointer', None)
    return 'rna:' + str(int(pointer())) if callable(pointer) else 'python:' + str(id(rna))


def frame_snapshot(host, graph):
    scene, layer = host.scene, host.view_layer
    units = scene.unit_settings
    scale = host._scale()
    return {'scene': str(scene.name), 'scene_id': identity_pointer(scene), 'view_layer': str(layer.name),
            'view_layer_id': identity_pointer(layer), 'depsgraph_id': identity_pointer(graph),
            'frame': int(scene.frame_current), 'subframe': float(scene.frame_subframe),
            'scale_length': scale, 'unit_settings': {'scale_length': scale, 'system': str(units.system),
                                                     'length_unit': str(units.length_unit)}}


def graph_updates(graph):
    rows = []
    for event in getattr(graph, 'updates', ()):
        rna = event.id
        source = getattr(rna, 'original', None) or rna
        rows.append({'id': identity_pointer(source), 'session_uid': getattr(source, 'session_uid', None),
                     'name': str(getattr(source, 'name_full', getattr(source, 'name', ''))),
                     'geometry': bool(event.is_updated_geometry), 'transform': bool(event.is_updated_transform),
                     'shading': bool(getattr(event, 'is_updated_shading', False))})
    return rows


def read_corners(evaluated):
    try:
        values = [[float(point[k]) for k in range(3)] for point in evaluated.bound_box]
    except (AttributeError, ReferenceError, RuntimeError, TypeError, ValueError, OverflowError, IndexError):
        return None, None
    if all(math.isfinite(v) for point in values for v in point):
        return values, [[v.hex() for v in point] for point in values]
    return None, [[v.hex() for v in point] for point in values]


def read_counts(evaluated):
    data = getattr(evaluated, 'data', None)
    try:
        vertices, loops, polygons = len(data.vertices), len(data.loops), len(data.polygons)
    except (AttributeError, ReferenceError, RuntimeError, TypeError):
        return {'vertices': None, 'loops': None, 'polygons': None, 'triangle_upper': None}
    return {'vertices': vertices, 'loops': loops, 'polygons': polygons,
            'triangle_upper': max(0, loops - 2 * polygons)}


def read_directory_object(host, obj, graph, frame, ident, display, ordinal, runtime):
    matrix_fn = runtime['_matrix']
    oid = host.object_id(obj)
    evaluated = obj.evaluated_get(graph)
    if not bool(getattr(evaluated, 'is_evaluated', True)):
        # Full product capture rejects an object without current evaluated evidence.
        raise ValueError('diagnostic_current_evaluation_missing:' + oid)
    matrix = matrix_fn(evaluated.matrix_world)
    corners, corner_hex = read_corners(evaluated)
    counts = read_counts(evaluated)
    outline = runtime['_acquisition_bounds'](corners, matrix, frame['scale_length'])
    tight, axes, reason = direct_bounds(corners, matrix, frame['scale_length'], outline)
    if outline is None and corners is None and corner_hex is not None:
        reason = 'nonfinite_RNA_corner'
    static_started = time.perf_counter_ns()
    native_static = {'eligible': False, 'source_mode': None, 'error': None}
    try:
        static_eval, _, static_matrix, static_bounds, source_mode = host._acquisition_directory_source(
            obj, graph, frame['scale_length'], allow_hidden=False)
    except (runtime['BlenderHostError'], AttributeError, ReferenceError, RuntimeError, TypeError, ValueError) as error:
        native_static['error'] = str(error)
    else:
        if (runtime['_same_rna'](static_eval, evaluated)
                and runtime['_digest'](static_matrix) == runtime['_digest'](matrix)
                and runtime['_digest'](static_bounds) == runtime['_digest'](outline)):
            native_static.update(eligible=True, source_mode=source_mode)
        else:
            native_static['error'] = 'acquisition_directory_read_not_bound_to_same_sample'
    static_stage = interval(static_started)
    row = {'ordinal': ordinal, 'name': obj.name, 'object_id': oid, 'instance_id': ident['object_instances'][oid],
           'evaluated_id': identity_pointer(evaluated), 'evaluated_data_id': identity_pointer(evaluated.data),
           'original_data_id': identity_pointer(obj.data), 'static_probe_stage': static_stage,
           'guards_digest': runtime['_digest'](host._guard_description(obj)),
           'matrix_world': matrix, 'corners_local': corners, 'corners_local_binary64': corner_hex,
           'rna_counts': counts, 'static_directory': native_static,
           'display': display, 'outward_world_bounds': outline,
           'axis_separable': not any(len(x) > 1 for x in axes), 'axis_support': axes,
           'tight_candidate_world': tight,
           'tight_candidate_bits': bounds_bits(tight) if tight is not None else None,
           'needs_vertices': tight is None, 'tight_fallback_reason': reason,
           'tight_outside_static_guard': tight is not None and not native_static['eligible']}
    return evaluated, row, static_stage


def ordered_limits(points):
    # Naive Python min/max use the first equal value. Min/max NumPy reduction
    # (the old camera) is separately checked against all received raw world rows.
    return [[reduce(point[axis] for point in points) for axis in range(3)] for reduce in (min, max)]


def capture_vertices(evaluated, matrix, scale, checkpoint, totals, *, target=False):
    stages = {}
    local, world, triangles = [], [], None
    checkpoint()
    started = time.perf_counter_ns()
    totals['to_mesh_attempts'] += 1
    mesh = evaluated.to_mesh()
    stages['to_mesh'] = interval(started)
    if mesh is None:
        raise ValueError('diagnostic_to_mesh_missing')
    totals['to_mesh_allocations'] += 1
    try:
        if totals['vertices_read'] + len(mesh.vertices) > 500_000:
            raise ValueError('diagnostic_vertex_budget_exceeded')
        started = time.perf_counter_ns()
        for n, vertex in enumerate(mesh.vertices):
            if n % 128 == 0:
                checkpoint()
            point = [float(vertex.co[i]) for i in range(3)]
            if not all(math.isfinite(x) for x in point):
                raise ValueError('diagnostic_nonfinite_local_vertex')
            local.append(point)
        totals['vertices_read'] += len(local)
        stages['read_local_vertices'] = interval(started)
        if len(local) < 3:
            raise ValueError('diagnostic_mesh_requires_three_vertices')
        started = time.perf_counter_ns()
        for n, point in enumerate(local):
            if n % 128 == 0:
                checkpoint()
            transformed = world_point(matrix, point, scale)
            if not all(math.isfinite(value) for value in transformed):
                raise ValueError('diagnostic_nonfinite_world_vertex')
            world.append(transformed)
        totals['world_transforms'] += len(world)
        stages['world_transforms'] = interval(started)
        started = time.perf_counter_ns()
        bounds = ordered_limits(world)
        stages['world_bounds_reduction'] = interval(started)
        if target:
            checkpoint()
            started = time.perf_counter_ns()
            mesh.calc_loop_triangles()
            totals['triangulations'] += 1
            if totals['triangle_rows_read'] + len(mesh.loop_triangles) > 1_000_000:
                raise ValueError('diagnostic_target_triangle_budget_exceeded')
            stages['target_triangulation'] = interval(started)
            started = time.perf_counter_ns()
            triangles = []
            for n, triangle in enumerate(mesh.loop_triangles):
                if n % 128 == 0:
                    checkpoint()
                face = [int(x) for x in triangle.vertices]
                if len(face) != 3 or min(face) < 0 or max(face) >= len(local):
                    raise ValueError('diagnostic_invalid_target_triangle')
                triangles.append(face)
            if not triangles:
                raise ValueError('diagnostic_empty_target_triangles')
            totals['triangle_rows_read'] += len(triangles)
            stages['target_triangle_rows'] = interval(started)
    finally:
        started = time.perf_counter_ns()
        totals['clear_attempts'] += 1
        evaluated.to_mesh_clear()
        totals['to_mesh_clear'] += 1
        stages['to_mesh_clear'] = interval(started)
    checkpoint()
    return {'local_vertices': local, 'world_vertices': world, 'tight_world_bounds': bounds,
            'tight_world_bounds_bits': bounds_bits(bounds), 'target_triangles': triangles, 'stages': stages}


def load_queries(host, queries, objects):
    if type(queries) is not list or len(queries) != 2:
        raise ValueError('diagnostic_two_queries_required')

    def selector(looking_for):
        if type(looking_for) is not dict or set(looking_for) not in ({'id'}, {'name'}):
            raise ValueError('diagnostic_explicit_selector_required')
        key, value = next(iter(looking_for.items()))
        if type(value) is not str or not value.strip() or len(value.encode('utf8')) > 256:
            raise ValueError('diagnostic_invalid_selector_value')
        matches = [i for i, obj in enumerate(objects) if (host.object_id(obj) if key == 'id' else obj.name) == value]
        if len(matches) != 1:
            raise ValueError('diagnostic_selector_not_unique')
        return matches[0]

    selected = []
    for q in queries:
        if (type(q) is not dict or set(q) != {'mode', 'region', 'reference', 'requested_facts'}
                or q['mode'] != 'source_region' or q['requested_facts'] != ['surface_proximity']
                or type(q['region']) is not dict or set(q['region']) != {'object', 'world_box_m'}):
            raise ValueError('diagnostic_source_region_query_contract')
        a, b = selector(q['region']['object']), selector(q['reference'])
        if a == b:
            raise ValueError('diagnostic_target_reference_same_object')
        bounds = host._source_region_pair_box(q['region']['world_box_m'])
        selected.append({'query': q, 'world_box_m': bounds, 'target_ordinal': a, 'reference_ordinal': b})
    if len({row['target_ordinal'] for row in selected}) != len(selected):
        raise ValueError('diagnostic_targets_must_be_distinct')
    return selected


def fresh_tally():
    return dict.fromkeys(('to_mesh_attempts', 'to_mesh_allocations', 'clear_attempts', 'to_mesh_clear',
                          'vertices_read', 'world_transforms', 'triangulations', 'triangle_rows_read'), 0)


def diagnose(host, queries, deadline_ns):
    """Record the one-lock, one-depsgraph causal window. No raster, model or save."""
    host._main_thread()
    if type(deadline_ns) is not int or deadline_ns <= 0:
        raise ValueError('diagnostic_deadline_required')

    def checkpoint():
        if time.perf_counter_ns() >= deadline_ns:
            raise ValueError('diagnostic_deadline_expired')

    runtime = host._capture.__func__.__globals__
    same, hash_payload = runtime['_same_rna'], runtime['_digest']
    stages = {}
    checkpoint()
    with host._lock:
        started = time.perf_counter_ns()
        checkpoint()
        graph_started = time.perf_counter_ns()
        graph = host._depsgraph()
        stages['depsgraph_update_and_get'] = interval(graph_started)
        checkpoint()
        meta = time.perf_counter_ns()
        frame = frame_snapshot(host, graph)
        scale = frame['scale_length']
        objects = host._objects(graph)
        ids = [host.object_id(o) for o in objects]
        ident = host._identity_metadata(objects)
        display = host._display_snapshot(objects)
        updates = graph_updates(graph)
        if (ident is None or display is None or display.get('status') != 'captured'
                or [row['host_id'] for row in display['objects']] != ids
                or any(type(row.get('visible_get')) is not bool for row in display['objects'])):
            raise ValueError('diagnostic_current_identity_and_display_required')
        selected = load_queries(host, queries, objects)
        targets = {row['target_ordinal'] for row in selected}
        stages['frame_identity_geometry_directory_and_display'] = interval(meta)

        arrays, directory, static_timings = [], [], []
        cheap_started = time.perf_counter_ns()
        for ordinal, (obj, display_row) in enumerate(zip(objects, display['objects'])):
            checkpoint()
            ev, row, static_stage = read_directory_object(host, obj, graph, frame, ident, display_row, ordinal, runtime)
            arrays.append(ev)
            directory.append(row)
            static_timings.append(static_stage)
        stages['RNA_directory_and_bound_candidates'] = interval(cheap_started)

        fallback_counter = fresh_tally()
        fallbacks = []
        fallback_started = time.perf_counter_ns()
        for ev, row in zip(arrays, directory):
            if not row['needs_vertices']:
                continue
            checkpoint()
            got = capture_vertices(ev, row['matrix_world'], scale, checkpoint, fallback_counter)
            fallbacks.append({k: got[k] for k in ('tight_world_bounds', 'tight_world_bounds_bits', 'world_vertices', 'stages')}
                             | {'ordinal': row['ordinal'], 'vertices_scanned': len(got['world_vertices']),
                                'reason': row['tight_fallback_reason']})
        stages['point_only_actual_fallback'] = interval(fallback_started)

        truth_counter = fresh_tally()
        truth = []
        truth_started = time.perf_counter_ns()
        for ev, row in zip(arrays, directory):
            checkpoint()
            got = capture_vertices(ev, row['matrix_world'], scale, checkpoint, truth_counter,
                                   target=row['ordinal'] in targets)
            truth.append(got | {'ordinal': row['ordinal'], 'object_id': row['object_id']})
        stages['independent_full_vertex_truth_including_required_target_triangles'] = interval(truth_started)
        selected_started = time.perf_counter_ns()
        for row in selected:
            obj = truth[row['target_ordinal']]
            low, high = (row['world_box_m'][side] for side in ('min', 'max'))
            inside = [all(a <= value <= b for a, value, b in zip(low, point, high)) for point in obj['world_vertices']]
            faces = [i for i, face in enumerate(obj['target_triangles']) if all(inside[v] for v in face)]
            if not 1 <= len(faces) <= 4096:
                raise ValueError('diagnostic_target_source_selection_outside_budget')
            row['source_triangle_indices'] = faces
        stages['resolve_target_source_closed_boxes'] = interval(selected_started)

        verify_started = time.perf_counter_ns()
        post_objects = host._objects(graph)
        post_graph = getattr(host.view_layer, 'depsgraph', None)
        current_graph_same = post_graph is None or same(graph, post_graph)
        default_context_same = not getattr(host, '_default_scene', False) or same(host.bpy.context.scene, host.scene)
        if default_context_same and getattr(host, '_default_view_layer', False):
            default_context_same = same(host.bpy.context.view_layer, host.view_layer)
        if (not current_graph_same or not default_context_same or host._identity_metadata(post_objects) != ident
                or [host.object_id(o) for o in post_objects] != ids
                or not all(same(a, b) for a, b in zip(objects, post_objects))
                or hash_payload(frame_snapshot(host, graph)) != hash_payload(frame)
                or graph_updates(graph) != updates or host._display_snapshot(post_objects) != display):
            raise ValueError('diagnostic_current_frame_identity_graph_or_display_changed')
        for obj, ev, row in zip(post_objects, arrays, directory):
            checkpoint()
            new = obj.evaluated_get(graph)
            if (not same(ev, new) or identity_pointer(new.data) != row['evaluated_data_id']
                    or identity_pointer(obj.data) != row['original_data_id']
                    or hash_payload(host._guard_description(obj)) != row['guards_digest']
                    or hash_payload(runtime['_matrix'](new.matrix_world)) != hash_payload(row['matrix_world'])
                    or read_counts(new) != row['rna_counts'] or read_corners(new)[1] != row['corners_local_binary64']):
                raise ValueError('diagnostic_same_window_pose_or_source_row_changed:' + row['object_id'])
        stages['same_window_final_recheck'] = interval(verify_started)
        stages['one_locked_host_window'] = interval(started)
        work = {'directory_objects': len(directory), 'depsgraph_fetches': 1,
                'static_directory_objects': sum(row['static_directory']['eligible'] for row in directory),
                'axis_separable_objects': sum(row['axis_separable'] for row in directory),
                'tight_numeric_candidates': sum(row['tight_candidate_world'] is not None for row in directory),
                'current_outward_objects': sum(row['outward_world_bounds'] is not None for row in directory),
                'point_only_fallback_objects': len(fallbacks), 'whole_truth_objects': len(truth),
                'target_objects': len(targets), 'static_directory_probe_ns': sum(s['elapsed_ns'] for s in static_timings),
                'point_only_fallback': fallback_counter, 'full_vertex_truth_and_target_faces': truth_counter}
        checkpoint()
        return {'schema': DIAGNOSTIC_SCHEMA, 'status': 'complete', 'frame': frame, 'identity': ident, 'display': display,
                'objects': directory, 'truth': truth, 'queries': selected, 'fallbacks': fallbacks,
                'graph_updates': updates, 'work': work, 'stages': stages, 'prepost_equal': True}
