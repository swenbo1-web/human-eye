"""Independent consumer for the explicit dense verification capability."""
import json, math
from fractions import Fraction
from .nonplanar_exact import ExactLocalIndex, binding as independent_binding, require
from .nonplanar_exact import validate_view, reserved_for
import time


def fields(value, keys):
    require(type(value) is dict and set(value) == set(keys.split()), 'protocol_fields')


def close(actual, expected):
    if isinstance(expected, (list, tuple)):
        return type(actual) is list and len(actual) == len(expected) and all(close(a, b) for a, b in zip(actual, expected))
    return type(actual) in (float, int) and math.isfinite(actual) and abs(actual-expected) <= max(
        64*max(math.ulp(float(actual)), math.ulp(float(expected))), 1e-12*max(abs(actual), abs(expected)))


def stable_dot(a, b):
    return math.fsum(x*y for x, y in zip(a, b))


def normalized(v):
    length = math.hypot(*v)
    require(math.isfinite(length) and length > 1e-15, 'direction_degenerate')
    return [x/length for x in v]


def interval(point, axis):
    # Independent enclosure reconstruction: no producer imports or calls.
    bounds = [0., 0.]
    for value, coefficient in zip(point, axis):
        product = value*coefficient
        require(math.isfinite(product), 'projection_overflow')
        for k, sign in enumerate((-math.inf, math.inf)):
            bounds[k] = math.nextafter(bounds[k]+math.nextafter(product, sign), sign)
            require(math.isfinite(bounds[k]), 'projection_overflow')
    return bounds


def reconstructed_frame(native, center, right, up, direction, span):
    depth = [stable_dot(subtract(p, center), direction) for o in native['objects'] for p in o['world_vertices']]
    margin = max(span, max(depth)-min(depth))/8
    distance = max(depth)+margin
    return dict(center_bu=center, direction=direction, right=right, up=up,
        camera_location_bu=[center[k]+distance*direction[k] for k in range(3)],
        ortho_scale_bu=span, clip_start_bu=margin/4, clip_end_bu=distance-min(depth)+margin)


def decision(result, native, object_id, edges, mode, deadline):
    """Rebuild the entire finite search before independently replaying proofs."""
    fields(result, 'schema selected candidates native_binding_sha256 binding_scope sampling_features sampling_policy '
        'locality_work_reserved max_locality_work locality_policy search_complete combined_triangle_tests_reserved '
        'max_triangle_tests combined_box_tests_reserved combined_projection_ops_reserved maximum_candidates maximum_images execution_authority'
        + (' acceleration_mode index_build_reservations index_build_units_reserved index_node_slots_reserved '
           'index_node_tests_reserved index_packet_bytes' if 'index_build_reservations' in result else ''))
    require(result['schema'] == 'bounded-nonplanar-plan-v1'
        and result['binding_scope'] == 'outer_raw_native_display_epoch_protocol'
        and result['sampling_policy'] == 'three_per_exact_collinear_coplanar_feature'
        and result['locality_policy'] == 'visual_nearplanar' and result['search_complete'] is True
        and result['max_locality_work'] == 32768 and result['max_triangle_tests'] == 8192
        and result['maximum_candidates'] == 4 and result['maximum_images'] == 2
        and result['execution_authority'] is False, 'plan_policy')
    require(mode in ('nonplanar_boundary_v1', 'nonplanar_dense_v1'), 'mode')
    target = next(o for o in native['objects'] if o['object_id'] == object_id)
    vertices = target['world_vertices']
    incident = {}; degree = {}
    for i, face in enumerate(target['faces']):
        for j in range(3):
            incident.setdefault(frozenset((face[j], face[(j+1)%3])), []).append(i)
    normals = []
    require(3 <= len(edges) <= 64 and len({frozenset(e) for e in edges}) == len(edges), 'boundary_members')
    for a, b in edges:
        require(type(a) is int and type(b) is int and a != b and 0 <= a < len(vertices) and 0 <= b < len(vertices), 'boundary_indices')
        degree[a] = degree.get(a, 0)+1; degree[b] = degree.get(b, 0)+1
        adjacent = incident.get(frozenset((a, b)), [])
        require(len(adjacent) == 1, 'boundary_adjacency')
        p, q, r = [vertices[v] for v in target['faces'][adjacent[0]]]
        normal = normalized(cross(subtract(q, p), subtract(r, p)))
        length = math.dist(vertices[a], vertices[b])
        normals.append([length*x for x in normal])
    require(all(v == 2 for v in degree.values()), 'boundary_closed')
    connected = {edges[0][0]}
    for _ in edges:
        for a, b in edges:
            if a in connected or b in connected:
                connected.update((a, b))
    require(connected == set(degree), 'boundary_component')
    mean = [math.fsum(v[k] for v in normals) for k in range(3)]
    require(math.hypot(*mean) > .1*sum(math.hypot(*v) for v in normals), 'normal_cancellation')
    mean = normalized(mean); directions = []
    for direction in (mean, [-x for x in mean], [0., 0., 1.], [0., 1., 0.]):
        if not any(stable_dot(direction, d) > 1-1e-10 for d in directions):
            directions.append(direction)
    rows = result['candidates']
    require(type(rows) is list and len(rows) == len(directions), 'candidate_completeness')
    points = [vertices[i] for i in sorted(degree)]
    all_points = [p for o in native['objects'] for p in o['world_vertices']]
    center = [min(p[k] for p in points)/2+max(p[k] for p in points)/2 for k in range(3)]
    all_center = [min(p[k] for p in all_points)/2+max(p[k] for p in all_points)/2 for k in range(3)]
    features = result['sampling_features']
    require(type(features) is list and 3 <= len(features) <= 64, 'feature_budget')
    for feature in features:
        fields(feature, 'edge source_edges')
    boxes = projections = nodes = reservation_count = 0
    selected = result['selected']
    for row, direction in zip(rows, directions):
        require(time.perf_counter_ns() < deadline, 'deadline_expired')
        keys = 'direction right up center span overview_span projection samples visible_count reason tests_reserved local_surfaces'
        if row == selected:
            keys += ' overview_frame detail_frame'
        if 'acceleration' in row:
            keys += ' acceleration'
        fields(row, keys)
        d = normalized(direction)
        right = normalized([-d[1], d[0], 0.] if math.hypot(d[0], d[1]) > 1e-10 else [-1., 0., 0.])
        up = cross(d, right)
        require(all(close(row[k], v) for k, v in (('direction', d), ('right', right), ('up', up), ('center', center))), 'basis_disagrees')
        projected = {i: [stable_dot(subtract(vertices[i], center), axis) for axis in (right, up)] for i in degree}
        widths = [max(p[k] for p in projected.values())-min(p[k] for p in projected.values()) for k in (0, 1)]
        span = 1.6*max(widths); width = min(widths)
        overview = 2.5*max(abs(stable_dot(subtract(p, all_center), axis)) for p in all_points for axis in (right, up))
        require(span > 0 and overview > 0 and math.isfinite(span+overview), 'projection_degenerate')
        require(width > 64*max(math.ulp(float(x)) for p in points for x in p) or width == 0, 'projection_unrepresentable')
        fields(row['projection'], 'overview_px detail_px')
        require(close(row['span'], span) and close(row['overview_span'], overview)
            and close(row['projection']['overview_px'], 384*width/overview)
            and close(row['projection']['detail_px'], 384*width/span), 'projection_disagrees')
        expected = 'no_projection_gain'; staged = []
        gain = 384*width/overview < 16 <= 384*width/span and overview/span >= 2
        if gain:
            ambiguous = False
            def orient(p, q, r):
                return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
            for i, (a, b) in enumerate(edges):
                for c, e in edges[i+1:]:
                    if {a, b} & {c, e}:
                        continue
                    p, q, r, s = [projected[j] for j in (a, b, c, e)]
                    if any(max(p[k], q[k]) < min(r[k], s[k]) or max(r[k], s[k]) < min(p[k], q[k]) for k in (0, 1)):
                        continue
                    o = [orient(p, q, r), orient(p, q, s), orient(r, s, p), orient(r, s, q)]
                    eps = span*span*1e-12
                    ambiguous |= (min(o[:2]) <= eps and max(o[:2]) >= -eps
                        and min(o[2:]) <= eps and max(o[2:]) >= -eps)
            expected = 'ambiguous_projected_boundary' if ambiguous else 'boundary_not_visible_enough'
            if not ambiguous:
                for feature in features:
                    a, b = feature['edge']; dx, dy = subtract(projected[b], projected[a])
                    length = math.hypot(dx, dy)
                    if length <= span/64:
                        expected = 'edge_subpixel'; staged = []; break
                    offset = [span/128*(-dy*right[k]+dx*up[k])/length for k in range(3)]
                    for t in (.25, .5, .75):
                        mid = [vertices[a][k]*(1-t)+vertices[b][k]*t for k in range(3)]
                        staged.append([[mid[k]+sign*offset[k] for k in range(3)] for sign in (-1, 1)])
        if staged:
            boxes += len(staged)*2*len(native['objects'])*3
            projections += (len(all_points)+len(staged)*2)*6
            bounds = {}
            for obj in native['objects']:
                projected_points = [[interval(p, axis) for p in obj['world_vertices']] for axis in (right, up)]
                bounds[obj['object_id']] = [[min(v[0] for v in values), max(v[1] for v in values)] for values in projected_points]
            require(type(row['samples']) is list and len(row['samples']) == len(staged), 'samples_complete')
            used = set()
            for sample, pair in zip(row['samples'], staged):
                fields(sample, 'edge source_edge pair possible_objects visible' + (' index_queries' if 'acceleration' in row else ''))
                require(type(sample['visible']) is bool and close(sample['pair'], pair), 'sample_geometry')
                wanted = []
                for point in pair:
                    q = [interval(point, axis) for axis in (right, up)]
                    wanted.append([name for name, box in bounds.items() if all(not (q[k][1] < box[k][0] or q[k][0] > box[k][1]) for k in (0, 1))])
                require(sample['possible_objects'] == wanted, 'object_filter_disagrees')
                for ids in wanted:
                    used.update(ids)
            indexed = {o['object_id'] for o in native['objects'] if o['object_id'] in used and len(o['faces']) >= 26}
            acceleration = row.get('acceleration')
            require((acceleration is not None) == (bool(indexed) and mode == 'nonplanar_dense_v1'), 'index_dispatch')
            if acceleration is not None:
                fields(acceleration, 'schema indices queries complete reason')
                require(acceleration['complete'] is True and acceleration['reason'] is None
                    and set(acceleration['indices']) == indexed and len(acceleration['queries']) == 2*len(staged), 'index_complete')
                for index in acceleration['indices'].values():
                    fields(index, 'schema object_id source_binding right up vertex_count face_count leaf_size nodes build_units_reserved node_slots_reserved reservation_index')
                    reservation_count += 1
                for sample_id, sample in enumerate(row['samples']):
                    require(sample['index_queries'] == [2*sample_id, 2*sample_id+1], 'query_completeness')
                for query in acceleration['queries']:
                    fields(query, 'point possible_objects filters traces complete')
                    nodes += 2*sum(len(trace) for trace in query['traces'].values())
            for proof in row['local_surfaces']:
                fields(proof, 'edge seed_face face_ids radius visited_face_count scope policy max_plane_deviation max_normal_sine')
            count = sum(sample['visible'] for sample in row['samples'])
            expected = 'visible_boundary_gain' if count >= max(8, math.ceil(len(staged)*2/3)) else 'boundary_not_visible_enough'
            require(type(row['visible_count']) is int and row['visible_count'] == count, 'visible_count')
        else:
            require(row['samples'] == [] and row['local_surfaces'] == [] and row['tests_reserved'] == 0
                and row['visible_count'] == 0 and 'acceleration' not in row, 'unexpected_work')
        require(row['reason'] == expected, 'decision_reason')
    require(boxes+nodes == result['combined_box_tests_reserved'] <= 32768
        and projections == result['combined_projection_ops_reserved'] <= 65536, 'broad_work_accounting')
    if 'index_build_reservations' in result:
        require(mode == 'nonplanar_dense_v1' and result['acceleration_mode'] == 'auto'
            and len(result['index_build_reservations']) == reservation_count, 'index_mode')
        for reservation in result['index_build_reservations']:
            fields(reservation, 'object_id face_count right up build_units_reserved node_slots_reserved')
    else:
        require(reservation_count == 0, 'index_ledger_missing')
    # The geometric witness replay never calls this producer's planner.
    work = replay(result, native, object_id, edges)
    valid = [r for r in rows if r['reason'] == 'visible_boundary_gain']
    best = max(valid, key=lambda r: (r['visible_count'], r['projection']['detail_px']), default=None)
    require(selected == best, 'selected_candidate_disagrees')
    row = best or rows[0]
    overview_frame = reconstructed_frame(native, all_center, row['right'], row['up'], row['direction'], row['overview_span'])
    detail_frame = None if best is None else reconstructed_frame(native, center, row['right'], row['up'], row['direction'], row['span'])
    if best is not None:
        for key, expected_frame in (('overview_frame', overview_frame), ('detail_frame', detail_frame)):
            require(set(best[key]) == set(expected_frame) and all(close(best[key][k], v) for k, v in expected_frame.items()), 'planned_frame_disagrees')
    require(time.perf_counter_ns() < deadline, 'deadline_expired')
    return work, overview_frame, detail_frame

def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]

def dot(a, b):
    return sum((x * y for x, y in zip(a, b)))

def subtract(a, b):
    return [x - y for x, y in zip(a, b)]

def ray(native, point, direction, allowed_objects=None, *, with_depth=False, allowed_faces=None):
    """3D Moller line intersection; no producer projection or depth routine."""
    hits = []
    for obj in native['objects']:
        if allowed_objects is not None and obj['object_id'] not in allowed_objects:
            continue
        triangles = enumerate(obj['faces']) if allowed_faces is None or obj['object_id'] not in allowed_faces else ((index, obj['faces'][index]) for index in allowed_faces[obj['object_id']])
        for index, face in triangles:
            a, b, c = [obj['world_vertices'][i] for i in face]
            e1 = subtract(b, a)
            e2 = subtract(c, a)
            h = cross(direction, e2)
            det = dot(e1, h)
            if abs(det) <= 1e-12 * max(math.hypot(*e1) * math.hypot(*e2), 1e-300):
                continue
            s = subtract(point, a)
            u = dot(s, h) / det
            q = cross(s, e1)
            v = dot(direction, q) / det
            if min(u, v, 1 - u - v) < -1e-12:
                continue
            hits.append((dot(e2, q) / det, obj['object_id'], index))
    if not hits:
        return []
    depth = max((h[0] for h in hits))
    eps = 1e-09 * max(1.0, abs(depth))
    return [(obj, index, z) if with_depth else (obj, index) for z, obj, index in hits if depth - z <= eps]

def replay(result, native, object_id, edges):
    """Rebuild each proposed view's offsets and independently replay all rays."""
    require(result['selected'] is None or result['selected'] in result['candidates'], 'independent_certificate')
    vertices = next((o['world_vertices'] for o in native['objects'] if o['object_id'] == object_id))
    faces = next((o['faces'] for o in native['objects'] if o['object_id'] == object_id))
    reserved = 0
    require(result['native_binding_sha256'] == independent_binding(native, object_id, edges), 'independent_certificate')
    local = ExactLocalIndex(next((o for o in native['objects'] if o['object_id'] == object_id)), result['max_locality_work'], result['locality_policy'])
    features = local.validate_features(edges, result['sampling_features'])
    index_node_work = 0
    index_bytes = 0
    observed_indices = set()
    reservations = result.get('index_build_reservations', [])
    for row in result['candidates']:
        acceleration = row.get('acceleration')
        if not row['samples'] and acceleration is None:
            continue

        def exact_dot(v, axis):
            return sum((Fraction(x) * Fraction(y) for x, y in zip(v, axis)), Fraction(0))
        if acceleration is not None:
            bounds = {}
            coordinates = {}
            for obj in native['objects']:
                projected = [[exact_dot(v, axis) for v in obj['world_vertices']] for axis in (row['right'], row['up'])]
                coordinates[obj['object_id']] = projected
                bounds[obj['object_id']] = [[min(values), max(values)] for values in projected]
            index_node_work += validate_view(acceleration, native, row['right'], row['up'], result['native_binding_sha256'], coordinates, reservations, observed_indices)
            index_bytes += sum((len(json.dumps(index, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()) for index in acceleration['indices'].values()))
            index_bytes += len(json.dumps(acceleration['queries'], separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode())
            if not acceleration['complete']:
                require(not row['samples'] and (not result['search_complete']), 'independent_certificate')
        if not row['samples']:
            continue
        proofs = [local.reconstruct(edge, 4 * row['span'] / 128) for edge in edges]
        require(len(row['local_surfaces']) == len(proofs), 'independent_certificate')
        for claimed, rebuilt_proof in zip(row['local_surfaces'], proofs):
            expected_limit = rebuilt_proof['max_plane_deviation']
            require(abs(claimed['max_plane_deviation'] - expected_limit) <= 2 * math.ulp(expected_limit), 'independent_certificate')
            require({k: v for k, v in claimed.items() if k != 'max_plane_deviation'} == {k: v for k, v in rebuilt_proof.items() if k != 'max_plane_deviation'}, 'independent_certificate')
        local.reserve(row['tests_reserved'])
        local_by_edge = {tuple(sorted(proof['edge'])): proof for proof in proofs}
        if acceleration is None:
            bounds = {}
            for obj in native['objects']:
                coordinates = [[exact_dot(v, axis) for v in obj['world_vertices']] for axis in (row['right'], row['up'])]
                bounds[obj['object_id']] = [[min(values), max(values)] for values in coordinates]
        sample_index = 0
        producer_reserved = 0
        rebuilt = []
        visible = []
        for feature in features:
            a, b = feature['edge']
            delta = subtract(vertices[b], vertices[a])
            x = dot(delta, row['right'])
            y = dot(delta, row['up'])
            length = math.sqrt(x * x + y * y)
            require(length > row['span'] / 64, 'independent_certificate')
            off = [row['span'] / 128 / length * (-y * row['right'][k] + x * row['up'][k]) for k in range(3)]
            for num in (1, 2, 3):
                mid = [(vertices[a][k] * (4 - num) + vertices[b][k] * num) / 4 for k in range(3)]
                pair = [[mid[k] + sign * off[k] for k in range(3)] for sign in (-1, 1)]
                claim = row['samples'][sample_index]
                sample_index += 1
                native_edge = local.sample_source(feature, num)
                require(claim['edge'] == [a, b] and claim['source_edge'] == native_edge, 'independent_certificate')
                hits = []
                for side, (point, original_point, ids) in enumerate(zip(pair, claim['pair'], claim['possible_objects'])):
                    q = [exact_dot(original_point, axis) for axis in (row['right'], row['up'])]
                    possible = {name for name, box in bounds.items() if all((box[k][0] <= q[k] <= box[k][1] for k in (0, 1)))}
                    require(len(ids) == len(set(ids)) and set(ids) <= set(bounds) and (possible <= set(ids)), 'independent_certificate')
                    filters = None
                    if acceleration is not None:
                        ref = claim['index_queries'][side]
                        query = acceleration['queries'][ref]
                        require(query['complete'] and query['point'] == original_point and (query['possible_objects'] == ids), 'independent_certificate')
                        filters = query['filters']
                    producer_reserved += sum((len(filters[o['object_id']]) if filters is not None and o['object_id'] in filters else len(o['faces']) for o in native['objects'] if o['object_id'] in ids))
                    hits.append(ray(native, point, row['direction'], ids, with_depth=True, allowed_faces=filters))
                h0, h1 = hits
                proof = local_by_edge[tuple(sorted(native_edge))]
                value = not h0 and local.validate_hit(proof, pair[1], row['direction'], h1, object_id) or (not h1 and local.validate_hit(proof, pair[0], row['direction'], h0, object_id))
                rebuilt.append(pair)
                visible.append(bool(value))
        require(len(rebuilt) == len(row['samples']), 'independent_certificate')
        for sample, pair, v in zip(row['samples'], rebuilt, visible):
            require(sample['visible'] == v, 'independent_certificate')
            require(all((abs(x - y) <= row['span'] * 1e-10 for a, b in zip(sample['pair'], pair) for x, y in zip(a, b))), 'independent_certificate')
        require(sum(visible) == row['visible_count'], 'independent_certificate')
        require(row['tests_reserved'] == 2 * producer_reserved, 'independent_certificate')
        reserved += row['tests_reserved']
    require(reserved == result['combined_triangle_tests_reserved'] <= 8192, 'independent_certificate')
    require(local.work == result['locality_work_reserved'] <= 32768, 'independent_certificate')
    if 'index_build_reservations' in result:
        by_id = {o['object_id']: o for o in native['objects']}
        units = slots = 0
        for entry in reservations:
            require(entry['face_count'] == len(by_id[entry['object_id']]['faces']), 'independent_certificate')
            u, n = reserved_for(entry['face_count'])
            require(entry['build_units_reserved'] == u and entry['node_slots_reserved'] == n, 'independent_certificate')
            units += u
            slots += n
        require(units == result['index_build_units_reserved'] <= 65536, 'independent_certificate')
        require(slots == result['index_node_slots_reserved'] <= 4096, 'independent_certificate')
        require(index_node_work == result['index_node_tests_reserved'] <= result['combined_box_tests_reserved'], 'independent_certificate')
        require(index_bytes == result['index_packet_bytes'] <= 512 * 1024, 'independent_certificate')
    require(result['combined_box_tests_reserved'] <= 32768 and result['combined_projection_ops_reserved'] <= 65536, 'independent_certificate')
    require(len(result['candidates']) <= 4 and result['maximum_images'] == 2 and (result['execution_authority'] is False), 'independent_certificate')
    return reserved
