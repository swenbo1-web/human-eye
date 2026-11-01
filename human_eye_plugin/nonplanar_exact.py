"""Independent rational local/index certificates. Checks survive Python -O."""
from fractions import Fraction as Q
import hashlib, json, math

def require(test, reason):
    if not test:
        raise ValueError('nonplanar_' + reason)

def sub(a, b):
    return tuple((x - y for x, y in zip(a, b)))

def dot(a, b):
    return sum((x * y for x, y in zip(a, b)), Q(0))

def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])

def binding(native, object_id, edges):
    data = json.dumps({'native': native, 'object_id': object_id, 'edges': edges}, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')
    require(len(data) <= 1024 * 1024, 'independent_certificate')
    return hashlib.sha256(data).hexdigest()

def point_segment_sq(p, a, b):
    ab = sub(b, a)
    ap = sub(p, a)
    den = dot(ab, ab)
    t = min(Q(1), max(Q(0), dot(ap, ab) / den)) if den else Q(0)
    residual = tuple((ap[k] - t * ab[k] for k in range(3)))
    return dot(residual, residual)

def segment_sq(a, b, c, d):
    values = [point_segment_sq(p, x, y) for p, x, y in ((a, c, d), (b, c, d), (c, a, b), (d, a, b))]
    u, v, w = (sub(b, a), sub(d, c), sub(a, c))
    aa, bb, cc, dd, ee = (dot(u, u), dot(u, v), dot(v, v), dot(u, w), dot(v, w))
    determinant = aa * cc - bb * bb
    if determinant:
        s = (bb * ee - cc * dd) / determinant
        t = (aa * ee - bb * dd) / determinant
        if 0 <= s <= 1 and 0 <= t <= 1:
            residual = tuple((w[k] + s * u[k] - t * v[k] for k in range(3)))
            values.append(dot(residual, residual))
    return min(values)

class ExactLocalIndex:

    def __init__(self, target, maximum, policy='strict_coplanar'):
        require(type(maximum) is int and 0 <= maximum <= 32768, 'independent_certificate')
        require(policy in ('strict_coplanar', 'visual_nearplanar'), 'independent_certificate')
        self.policy = policy
        self.maximum = maximum
        self.work = 0
        self.points = [tuple((Q(x) for x in p)) for p in target['world_vertices']]
        self.faces = target['faces']
        self.links = {}
        self.normals = {}
        self.reserve(9 * len(self.faces))
        for i, face in enumerate(self.faces):
            require(len(face) == 3 and len(set(face)) == 3, 'independent_certificate')
            for j in range(3):
                a, b = (face[j], face[(j + 1) % 3])
                require(type(a) is int and type(b) is int and (0 <= a < len(self.points)) and (0 <= b < len(self.points)), 'independent_certificate')
                self.links.setdefault(frozenset((a, b)), []).append((i, a, b))

    def reserve(self, count):
        self.work += count
        require(self.work <= self.maximum, 'independent_certificate')

    def normal(self, index):
        if index not in self.normals:
            self.reserve(2)
            a, b, c = [self.points[v] for v in self.faces[index]]
            n = cross(sub(b, a), sub(c, a))
            require(dot(n, n) > Q('1e-30'), 'independent_certificate')
            self.normals[index] = n
        return self.normals[index]

    def reconstruct(self, edge, radius):
        a, b = edge
        start, end = (self.points[a], self.points[b])
        incident = self.links[frozenset(edge)]
        require(len(incident) == 1, 'independent_certificate')
        seed = incident[0][0]
        n = self.normal(seed)
        nsq = dot(n, n)
        length_sq = dot(sub(end, start), sub(end, start))
        require(length_sq > 0, 'independent_certificate')
        normal_sine = 1e-08 if self.policy == 'strict_coplanar' else 1 / 1024
        plane_limit = float(length_sq) ** 0.5 * 1e-10 if self.policy == 'strict_coplanar' else radius / 96
        radius_sq = Q(radius) ** 2
        pending = [seed]
        seen = {seed}
        accepted = []
        while pending:
            self.reserve(2)
            index = pending.pop(0)
            require(len(seen) <= 128, 'independent_certificate')
            other = self.normal(index)
            angle = cross(n, other)
            if dot(n, other) <= 0 or dot(angle, angle) > Q(normal_sine) ** 2 * nsq * dot(other, other):
                continue
            plane_squared = Q('1e-20') * length_sq if self.policy == 'strict_coplanar' else Q(plane_limit) ** 2
            if any((dot(n, sub(self.points[v], start)) ** 2 > plane_squared * nsq for v in self.faces[index])):
                continue
            accepted.append(index)
            face = self.faces[index]
            for i in range(3):
                self.reserve(2)
                x, y = (face[i], face[(i + 1) % 3])
                links = self.links[frozenset((x, y))]
                if len(links) != 2:
                    continue
                left, right = links
                if (left[1], left[2]) != (right[2], right[1]):
                    continue
                neighbour = right[0] if left[0] == index else left[0]
                if neighbour in seen:
                    continue
                if segment_sq(start, end, self.points[x], self.points[y]) > radius_sq:
                    continue
                seen.add(neighbour)
                pending.append(neighbour)
        return {'edge': list(edge), 'seed_face': seed, 'face_ids': sorted(accepted), 'radius': radius, 'visited_face_count': len(seen), 'scope': 'oriented_bounded_plane_capsule_connected', 'policy': self.policy, 'max_plane_deviation': plane_limit, 'max_normal_sine': normal_sine}

    def validate_hit(self, proof, point, direction, hits, object_id):
        if not hits:
            return False
        a, b = [self.points[v] for v in proof['edge']]
        for owner, index, depth in hits:
            if owner != object_id or index not in proof['face_ids']:
                return False
            actual = tuple((Q(point[k] + depth * direction[k]) for k in range(3)))
            if point_segment_sq(actual, a, b) > Q(proof['radius']) ** 2:
                return False
        return True

    def validate_features(self, edges, features):
        """Check a complete partition of native edges, without producer walk."""
        self.reserve(8 * len(edges))
        neighbours = {}
        normals = {}
        for a, b in edges:
            neighbours.setdefault(a, []).append(b)
            neighbours.setdefault(b, []).append(a)

        def qnormal(a, b):
            incident = self.links[frozenset((a, b))]
            require(len(incident) == 1, 'independent_certificate')
            face = incident[0][0]
            if face not in normals:
                x, y, z = [self.points[v] for v in self.faces[face]]
                normals[face] = cross(sub(y, x), sub(z, x))
            return normals[face]
        corners = set()
        for v, ns in neighbours.items():
            require(len(ns) == 2, 'independent_certificate')
            left, right = (sub(self.points[x], self.points[v]) for x in ns)
            a, b = (qnormal(v, x) for x in ns)
            if any(cross(left, right)) or dot(left, right) >= 0 or any(cross(a, b)) or (dot(a, b) <= 0):
                corners.add(v)
        require(len(corners) >= 3 and len(features) == len(corners), 'independent_certificate')
        require(features[0]['edge'][0] == min(corners, key=lambda v: self.points[v]), 'independent_certificate')
        require(self.points[features[0]['edge'][1]] < self.points[features[-1]['edge'][0]], 'independent_certificate')
        covered = []
        begins = []
        for i, feature in enumerate(features):
            start, end = feature['edge']
            chain = feature['source_edges']
            require(start in corners and end in corners and (start != end) and chain, 'independent_certificate')
            require(chain[0][0] == start and chain[-1][1] == end, 'independent_certificate')
            require(end == features[(i + 1) % len(features)]['edge'][0], 'independent_certificate')
            for j, (a, b) in enumerate(chain):
                require(b in neighbours[a], 'independent_certificate')
                if j:
                    require(a == chain[j - 1][1] and a not in corners, 'independent_certificate')
                covered.append(frozenset((a, b)))
            begins.append(start)
        require(len(set(begins)) == len(corners) and set(begins) == corners, 'independent_certificate')
        require(len(covered) == len(edges) and len(set(covered)) == len(edges), 'independent_certificate')
        require(set(covered) == {frozenset(edge) for edge in edges}, 'independent_certificate')
        return features

    def sample_source(self, feature, numerator):
        a, b = [self.points[v] for v in feature['edge']]
        point = tuple((((4 - numerator) * a[k] + numerator * b[k]) / 4 for k in range(3)))
        for x, y in feature['source_edges']:
            if point_segment_sq(point, self.points[x], self.points[y]) == 0:
                return [x, y]
        raise AssertionError('sample has no native source')

def reserved_for(count):
    height = 0
    capacity = 8
    while capacity < count:
        height += 1
        capacity *= 2
    slots = 2 ** (height + 1) - 1
    return (count * (height + 3) + slots, slots)

def validate_index(index, obj, right, up, binding, coordinates, reservations):
    require(index['schema'] == 'projected-triangle-bvh-v1' and index['leaf_size'] == 8, 'independent_certificate')
    require(index['object_id'] == obj['object_id'] and index['source_binding'] == binding, 'independent_certificate')
    require(index['right'] == right and index['up'] == up, 'independent_certificate')
    count = len(obj['faces'])
    require(index['face_count'] == count and index['vertex_count'] == len(obj['world_vertices']), 'independent_certificate')
    units, slots = reserved_for(count)
    require(index['build_units_reserved'] == units and index['node_slots_reserved'] == slots, 'independent_certificate')
    reservation = index['reservation_index']
    require(type(reservation) is int and 0 <= reservation < len(reservations), 'independent_certificate')
    require(reservations[reservation] == {'object_id': obj['object_id'], 'face_count': count, 'right': right, 'up': up, 'build_units_reserved': units, 'node_slots_reserved': slots}, 'independent_certificate')
    nodes = index['nodes']
    require(type(nodes) is list and 1 <= len(nodes) <= slots, 'independent_certificate')
    seen = set()
    faces = []
    pending = [0]
    while pending:
        number = pending.pop()
        require(type(number) is int and 0 <= number < len(nodes) and (number not in seen), 'independent_certificate')
        seen.add(number)
        node = nodes[number]
        require(type(node) is list and len(node) == 7, 'independent_certificate')
        require(all((type(v) in (int, float) and math.isfinite(v) for v in node[:4])), 'independent_certificate')
        require(node[0] <= node[2] and node[1] <= node[3], 'independent_certificate')
        left, right_id = node[4:6]
        require(type(left) is int and type(right_id) is int, 'independent_certificate')
        if left == -1:
            require(right_id == -1 and type(node[6]) is list and (1 <= len(node[6]) <= 8), 'independent_certificate')
            require(node[6] == sorted(set(node[6])), 'independent_certificate')
            for face_id in node[6]:
                require(type(face_id) is int and 0 <= face_id < count, 'independent_certificate')
                faces.append(face_id)
                face = obj['faces'][face_id]
                for axis in (0, 1):
                    low = min((coordinates[axis][v] for v in face))
                    high = max((coordinates[axis][v] for v in face))
                    pad = Q('4e-12') * (high - low)
                    require(Q(node[axis]) <= low - pad and Q(node[axis + 2]) >= high + pad, 'independent_certificate')
        else:
            require(node[6] == [] and 0 <= left < len(nodes) and (0 <= right_id < len(nodes)) and (left != right_id), 'independent_certificate')
            for child_id in (left, right_id):
                child = nodes[child_id]
                require(len(child) == 7, 'independent_certificate')
                require(all((node[k] <= child[k] and node[k + 2] >= child[k + 2] for k in (0, 1))), 'independent_certificate')
                pending.append(child_id)
    require(len(seen) == len(nodes) and len(faces) == count and (sorted(faces) == list(range(count))), 'independent_certificate')

def validate_query(index, query, name, right, up):
    trace = query['traces'][name]
    claimed = query['filters'][name]
    require(type(trace) is list and type(claimed) is list and (claimed == sorted(set(claimed))), 'independent_certificate')
    point = query['point']
    require(len(point) == 3, 'independent_certificate')
    projected = [sum((Q(v) * Q(a) for v, a in zip(point, axis)), Q(0)) for axis in (right, up)]
    records = {}
    for number, active in trace:
        require(type(number) is int and 0 <= number < len(index['nodes']) and (number not in records), 'independent_certificate')
        require(type(active) is bool, 'independent_certificate')
        records[number] = active
    require(0 in records or not query['complete'], 'independent_certificate')
    covered = set()
    pending = [0]
    visited = set()
    while pending:
        number = pending.pop()
        if number not in records:
            require(query['complete'] is False, 'independent_certificate')
            continue
        visited.add(number)
        node = index['nodes'][number]
        active = records[number]
        if not active:
            require(any((projected[k] < Q(node[k]) or projected[k] > Q(node[k + 2]) for k in (0, 1))), 'independent_certificate')
        elif node[4] == -1:
            covered.update(node[6])
        else:
            pending.extend((node[4], node[5]))
    require(visited == set(records) and sorted(covered) == claimed, 'independent_certificate')
    return 2 * len(trace)

def validate_view(acceleration, native, right, up, binding, coordinates, reservations, observed):
    if acceleration is None:
        return 0
    require(acceleration['schema'] == 'triangle-index-view-v1', 'independent_certificate')
    require(type(acceleration['complete']) is bool, 'independent_certificate')
    by_id = {o['object_id']: o for o in native['objects']}
    indices = acceleration['indices']
    require(set(indices) <= set(by_id), 'independent_certificate')
    for name, index in indices.items():
        validate_index(index, by_id[name], right, up, binding, coordinates[name], reservations)
        require(index['reservation_index'] not in observed, 'independent_certificate')
        observed.add(index['reservation_index'])
    work = 0
    for query in acceleration['queries']:
        require(type(query['complete']) is bool, 'independent_certificate')
        expected = set(query['possible_objects']) & set(indices)
        require(set(query['filters']) == set(query['traces']), 'independent_certificate')
        require(set(query['traces']) <= expected, 'independent_certificate')
        if query['complete']:
            require(set(query['traces']) == expected, 'independent_certificate')
        else:
            require(acceleration['complete'] is False, 'independent_certificate')
        for name in query['traces']:
            work += validate_query(indices[name], query, name, right, up)
    return work
