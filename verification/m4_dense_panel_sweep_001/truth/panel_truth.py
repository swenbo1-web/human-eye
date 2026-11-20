"""Recompute the exact dense-scene target and finite-view truth from frozen Blender arrays."""

from collections import defaultdict
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise
import json
from math import gcd, lcm, sqrt
from pathlib import Path
import sys
import time


HERE = Path(__file__).resolve().parent
ASSETS = Path('D:/he_m4_target_002/assets_01')
ASSET = ASSETS / 'main.blend'
GEOMETRY = ASSETS / 'main.GEOMETRY.json'
ASSET_SHA = '2d7c48f01665588bd7cfc93280ea50b559f4dc08196738c504ea56c88c75a164'
GEOMETRY_SHA = 'a48ef1b1634e1bbe66fbb49d47899581432d6bf4aebae5577ea5abdebf4b774d'
COUNTS = {'objects': 14, 'vertices': 3478, 'triangles': 6148}
DIRECTIONS = {'SCENE': (4, -4, 3), 'TOP': (0, 0, 1), 'LEFT': (-1, 0, 1),
              'RIGHT': (1, 0, 1), 'FRONT': (0, -1, 1), 'BACK': (0, 1, 1)}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def pin(path, expected=None):
    path = path.resolve()
    raw = path.read_bytes()
    digest = sha256(raw).hexdigest()
    require(expected is None or digest == expected, 'fixed_input_changed/' + str(path))
    return {'path': str(path), 'bytes': len(raw), 'sha256': digest}, raw


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b, strict=True))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def pairs(v):
    return pairwise((*v, v[0]))


def numeric_vector(point):
    out = [float(value) for value in point]
    require(tuple(map(Fraction, out)) == tuple(point), 'fixture_vector_not_losslessly_encodable')
    return out


def source_ranges(values):
    ranges = []
    for value in values:
        if not ranges or value != ranges[-1][1] + 1:
            ranges.append([value, value])
        else:
            ranges[-1][1] = value
    return ranges


def load_meshes(raw):
    source = json.loads(raw)
    require(source['frame'] == 1 and source['subframe'] == 0 and source['unit_system'] == 'METRIC'
            and source['scale_length'] == 1.0, 'fixed_scene_frame_or_units_changed')
    meshes = {}
    for index, obj in enumerate(source['objects']):
        name = obj['name']
        require(obj['asset_object_ordinal'] == obj['frozen_object_ordinal'] == index
                and name == obj['name_full'] and not obj['library_path'] and name not in meshes,
                'fixed_object_identity_invalid')
        vertices = tuple(tuple(map(Fraction, point)) for point in obj['vertices_world'])
        faces = tuple(tuple(face) for face in obj['source_triangles'])
        require(all(len(point) == 3 for point in vertices) and all(
            len(set(face)) == 3 and len(face) == 3
            and all(type(i) is int and 0 <= i < len(vertices) for i in face) for face in faces),
            'invalid_triangles/' + name)
        meshes[name] = (vertices, faces)
    require({'objects': len(meshes), 'vertices': sum(len(v) for v, _ in meshes.values()),
             'triangles': sum(len(f) for _, f in meshes.values())} == COUNTS, 'fixed_scene_size_changed')
    return meshes


def partition(mesh):
    """Connected components of indexed edges sharing an exact directed plane."""
    vertices, faces = mesh
    normals, planes, neighbor_by_edge = [], [], defaultdict(list)
    for face_index, face in enumerate(faces):
        a, b, c = (vertices[i] for i in face)
        normal = cross(sub(b, a), sub(c, a))
        require(any(normal), 'degenerate_input_triangle')
        scale = lcm(*(v.denominator for v in normal))
        integers = tuple(int(v * scale) for v in normal)
        divisor = gcd(*integers)
        primitive = tuple(value // divisor for value in integers)
        plane = (primitive, dot(primitive, a))
        normals.append(normal)
        planes.append(plane)
        for edge in pairs(face):
            neighbor_by_edge[(plane, tuple(sorted(edge)))].append(face_index)

    components, seen = [], set()
    for root, plane in enumerate(planes):
        if root in seen:
            continue
        todo, component = [root], []
        seen.add(root)
        while todo:
            face_index = todo.pop()
            component.append(face_index)
            for edge in pairs(faces[face_index]):
                for neighbor in neighbor_by_edge[(plane, tuple(sorted(edge)))]:
                    if neighbor not in seen:
                        seen.add(neighbor)
                        todo.append(neighbor)
        components.append((plane, sorted(component)))
    return components, normals


def boundary_rectangle(vertices, faces, component, twice_area):
    edges = defaultdict(list)
    for i in component:
        for edge in pairs(faces[i]):
            edges[tuple(sorted(edge))].append(edge)
    boundary = []
    for directed in edges.values():
        if len(directed) == 1:
            boundary.append(directed[0])
        elif len(directed) != 2 or directed[0] != directed[1][::-1]:
            return None
    successor = dict(boundary)
    if not successor or len(successor) != len(boundary) or set(successor.values()) != set(successor):
        return None
    start = min(successor)
    cycle = [start]
    for _ in range(len(boundary) - 1):
        successor_vertex = successor[cycle[-1]]
        if successor_vertex == start:
            return None
        cycle.append(successor_vertex)
    if successor[cycle[-1]] != start:
        return None
    ring = [vertices[i] for i in cycle]
    corner_indices = []
    for i, (a, b, c) in enumerate(zip(ring[-1:] + ring[:-1], ring, ring[1:] + ring[:1], strict=True)):
        incoming, outgoing = sub(b, a), sub(c, b)
        if any(cross(incoming, outgoing)):
            corner_indices.append(cycle[i])
        elif dot(incoming, outgoing) <= 0:
            return None
    if len(corner_indices) != 4:
        return None
    corners = [vertices[i] for i in corner_indices]
    a, b, c, d = corners
    u, v = sub(b, a), sub(d, a)
    if sub(c, d) != u or sub(c, b) != v or dot(u, v) != 0:
        return None
    if tuple(2 * element for element in cross(u, v)) != twice_area:
        return None
    for i in {j for face_index in component for j in faces[face_index]}:
        offset = sub(vertices[i], a)
        if not (0 <= dot(offset, u) <= dot(u, u) and 0 <= dot(offset, v) <= dot(v, v)):
            return None
    return corners, corner_indices


def clip(polygon, axis, sign, boundary):
    if not polygon:
        return []
    result = []
    for a, b in pairs(polygon):
        da, db = sign * (a[axis] - boundary), sign * (b[axis] - boundary)
        if da >= 0:
            result.append(a)
        if (da >= 0) != (db >= 0):
            fraction = da / (da - db)
            result.append(tuple(x + fraction * (y - x) for x, y in zip(a, b, strict=True)))
    return result


def visibility(meshes, object_name, component, corners, normal, direction):
    facing = dot(normal, direction)
    result = {'direction': direction, 'normal_dot_direction': str(facing),
              'tested_other_triangles': COUNTS['triangles'] - len(component) if facing > 0 else 0,
              'whole_region_clear': False, 'positive_area_occluders': []}
    if facing <= 0:
        return result | {'status': 'edge_on' if facing == 0 else 'back_facing'}

    # Project each source triangle to target-plane coordinates along the
    # orthographic viewing direction. The third coordinate is signed depth.
    origin, b, _, d = corners
    u, v = sub(b, origin), sub(d, origin)
    axes = tuple((axis, dot(axis, axis), dot(direction, axis)) for axis in (u, v))
    front_tested = 0
    own = set(component)
    hits = result['positive_area_occluders']
    for name, (vertices, faces) in meshes.items():
        offsets = [sub(p, origin) for p in vertices]
        depth_numerators = [dot(normal, r) for r in offsets]
        if max(depth_numerators) <= 0:
            continue
        chart = []
        for offset, distance in zip(offsets, depth_numerators, strict=True):
            depth = distance / facing
            chart.append(tuple((dot(offset, axis) - shift * depth) / size
                               for axis, size, shift in axes) + (depth,))
        for index, face in enumerate(faces):
            if name == object_name and index in own:
                continue
            points = [chart[i] for i in face]
            us, vs, ts = zip(*points, strict=True)
            if max(ts) <= 0:
                continue
            front_tested += 1
            if min(us) >= 1 or max(us) <= 0 or min(vs) >= 1 or max(vs) <= 0:
                continue
            for axis, sign, limit in ((2, 1, 0), (0, 1, 0), (0, -1, 1), (1, 1, 0), (1, -1, 1)):
                points = clip(points, axis, sign, limit)
            if len(points) < 3 or max(point[2] for point in points) <= 0:
                continue
            area = abs(sum(a[0] * b[1] - a[1] * b[0] for a, b in pairs(points))) / 2
            if area > 0:
                hits.append({'object_name': name, 'source_triangle_index': index,
                             'projected_area_m2_per_basis': str(area)})
    return result | {'whole_region_clear': not hits, 'positive_depth_triangles': front_tested,
                     'status': 'positive_area_occlusion' if hits else 'complete'}


def determine(meshes):
    all_components, qualified = [], []
    for name, mesh in meshes.items():
        components, normals = partition(mesh)
        for (normal, offset), component in components:
            twice_area = tuple(sum(normals[i][axis] for i in component) for axis in range(3))
            area_squared = dot(twice_area, twice_area) / 4
            rectangle = boundary_rectangle(*mesh, component, twice_area)
            row = {'object_name': name, 'source_triangle_id_ranges': source_ranges(component),
                   'source_triangle_count': len(component), 'plane_normal_integer': normal,
                   'plane_offset_exact': str(offset), 'area_squared_m4_exact': str(area_squared),
                   'rectangle_supported': rectangle is not None,
                   'eligible': rectangle is not None and area_squared == 1 and normal[2] >= 0}
            all_components.append(row)
            if not row['eligible']:
                continue
            corners, vertex_indices = rectangle
            center = tuple((a + c) / 2 for a, c in zip(corners[0], corners[2], strict=True))
            unit = sqrt(dot(normal, normal))
            proofs = {view: visibility(meshes, name, component, corners, normal, direction)
                      for view, direction in DIRECTIONS.items()}
            clear = [view for view, proof in proofs.items() if proof['whole_region_clear']]
            qualified.append(row | {'source_triangle_indices': component,
                             'vertex_indices': vertex_indices, 'area_squared_m4': 1, 'area_m2': 1.0,
                             'unit_normal': [v / unit for v in normal],
                             'center_world_m': numeric_vector(center),
                             'corners_world_m': [numeric_vector(point) for point in corners],
                             'finite_direction_proofs': proofs, 'eligible_complete_views': clear,
                             'expected_unknown_reason': (None if clear else 'positive_area_occlusion_all_front_views')})
    return all_components, qualified


def main():
    started = time.perf_counter_ns()
    asset, _ = pin(ASSET, ASSET_SHA)
    geometry, raw = pin(GEOMETRY, GEOMETRY_SHA)
    source, _ = pin(Path(__file__))
    meshes = load_meshes(raw)
    all_components, qualified = determine(meshes)
    result = {
        'schema': 'm4-dense-panel-sweep-independent-frozen-blender-truth-v1',
        'passed': True, 'asset_path': asset['path'], 'asset_sha256': ASSET_SHA,
        'geometry_sha256': GEOMETRY_SHA, 'counts': COUNTS, 'object_names': list(meshes),
        'source_pins': [source, asset, geometry], 'directions': DIRECTIONS,
        'conditions': {'area_min_m2': 1.0, 'area_max_m2': 1.0, 'normal_z_min': 0.0},
        'component_count': len(all_components), 'rectangles': sum(row['rectangle_supported'] for row in all_components),
        'all_components': all_components, 'eligible': qualified,
        'visibility_domain': 'Orthographic direction with positive signed occluder depth and nonzero exact projected area. Pixel readability requires separate actual-frame evidence.',
        'source_triangle_id_ranges_semantics': 'Object-local zero-based evaluated triangle IDs. Each pair is inclusive.',
    }
    output = Path(sys.argv[1]) if len(sys.argv) == 2 else HERE / 'CURRENT_TRUTH.json'
    with output.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({
        'sha256': pin(output)[0]['sha256'], 'components': len(all_components), 'regions': len(qualified),
        'elapsed_s': (time.perf_counter_ns() - started) / 1e9,
        'visibility': [{key: row[key] for key in ('object_name', 'source_triangle_id_ranges', 'eligible_complete_views')}
                       for row in qualified]}, sort_keys=True))


if __name__ == '__main__':
    main()
