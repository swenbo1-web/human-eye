"""Independent packet/native-row qualification and fixed-point checks, no product imports."""
from __future__ import annotations

from fractions import Fraction as Q
import hashlib
import itertools
import json
import re
import struct

from replay_common import ASSET_SHA, BOX, REFERENCE, TARGET, need, read


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode('utf-8')).hexdigest()


def numeric_bytes(rows):
    return b''.join(struct.pack('<d', float(x)) for row in rows for x in row)


def check_public(value, expected):
    for key in ('status', 'selected_triangle_count', 'source_triangle_a', 'source_triangle_b',
                'direction_status', 'coordinate_frame', 'unit', 'world_box_m'):
        need(value[key] == expected[key], 'public_field_changed:' + key)
    for key in ('distance_m', 'point_a_m', 'point_b_m', 'direction_a_to_b'):
        a, b = value[key], expected[key]
        if key == 'distance_m':
            a, b = [a], [b]
        need(numeric_bytes([a]) == numeric_bytes([b]), 'public_binary64_changed:' + key)
    return True


def qualify(capture, source_path, truth_path):
    """Rebuild the closed-box compact mesh independently from archived raw world vertices."""
    original = read(source_path)
    frozen = read(truth_path)
    need(original['source']['asset_sha256'] == ASSET_SHA, 'original_asset_identity')
    objects = {obj['name']: obj for obj in original['objects']}
    target, reference = objects[TARGET['name']], objects[REFERENCE['name']]
    src, ref = target['evaluated'], reference['evaluated']
    world, faces = src['vertices_world_m'], src['triangles']
    selected_vertices = [all(lo <= x <= hi for x, lo, hi in zip(v, BOX['min'], BOX['max'])) for v in world]
    rows = [i for i, face in enumerate(faces) if all(selected_vertices[v] for v in face)]
    vertex_rows = sorted({v for i in rows for v in faces[i]})
    inverse = {v: i for i, v in enumerate(vertex_rows)}
    original_faces = [faces[i] for i in rows]
    compact_faces = [[inverse[v] for v in face] for face in original_faces]
    compact_world = [world[i] for i in vertex_rows]
    region, whole, binding = capture['region'], capture['reference'], capture['binding']
    need(rows == frozen['regions']['high']['triangle_ids'] == region['source_triangle_indices'], 'complete_native_triangle_rows')
    need(len(rows) == 262 and len(vertex_rows) == 173, 'frozen_compact_counts')
    need(vertex_rows == region['source_vertex_indices'], 'complete_native_vertex_rows')
    need(original_faces == region['source_triangle_vertices'] and compact_faces == region['faces'], 'native_ordered_faces')
    need(numeric_bytes(compact_world) == numeric_bytes(region['vertices']), 'exact_original_world_vertices')
    need(whole['faces'] == ref['triangles'] and numeric_bytes(whole['vertices']) == numeric_bytes(ref['vertices_world_m']), 'exact_reference_geometry')
    need(region['source_vertex_count'] == len(world) and region['source_triangle_count'] == len(faces), 'source_scope_counts')
    need(binding['unit'] == 'm' and binding['coordinate_frame'] == 'world', 'world_meters')
    for key in ('frame', 'subframe', 'scale_length'):
        need(binding['source_frame'][key] == original['source'][key], 'frozen_source_frame:' + key)
    # Connector: live RNA instance; exporter: layer name plus historical RNA ID.
    # Cross-process RNA addresses are not a semantic layer-name comparison.
    need(re.fullmatch(r'rna:[0-9]+', binding['source_frame']['view_layer']) is not None,
         'current_native_view_layer_identity')
    for key, obj in (('target', target), ('reference', reference)):
        need(numeric_bytes(binding['world_matrices'][key]) == numeric_bytes(obj['matrix_world']), 'exact_matrix:' + key)
    need(binding['world_box_m'] == BOX and binding['target_selector'] == TARGET and binding['reference_selector'] == REFERENCE, 'fixed_request_binding')
    need(capture['payload_sha256'] == digest({k: capture[k] for k in ('schema','binding','region','reference')}), 'packet_canonical_digest')

    # Independent analytic certificate for this fixed Cube interior case.
    # Every native Cube triangle must tile one closed square face by its two
    # distinct corner triangles, with a common diagonal and opposite third corners.
    corners = {tuple(map(Q, v)) for v in whole['vertices']}
    need(corners == set(itertools.product((Q(-1), Q(1)), repeat=3)), 'cube_corners')
    planes = {}
    for i, f in enumerate(whole['faces']):
        pts = [tuple(map(Q, whole['vertices'][v])) for v in f]
        need(len(set(pts)) == 3, 'cube_triangle_degenerate')
        side = [(axis, pts[0][axis]) for axis in range(3) if len({p[axis] for p in pts}) == 1]
        need(len(side) == 1, 'cube_triangle_plane')
        planes.setdefault(side[0], []).append((i, set(pts)))
    need(len(planes) == 6, 'cube_six_faces')
    for (axis, value), pair in planes.items():
        need(len(pair) == 2, 'cube_two_triangles_per_face')
        a, b = pair[0][1], pair[1][1]
        shared = list(a & b)
        need(len(a | b) == 4 and len(shared) == 2, 'cube_complete_square')
        need(all(shared[0][k] != shared[1][k] for k in range(3) if k != axis), 'cube_shared_diagonal')
    points = [tuple(map(Q, p)) for p in compact_world]
    need(all(all(-1 < x < 1 for x in p) for p in points), 'selected_mesh_inside_cube')
    distances = {(axis, sign): min(1 - sign * p[axis] for p in points)
                 for axis in range(3) for sign in (-1, 1)}
    bound = min(distances.values())
    need(distances[(2, 1)] == bound, 'fixed_top_plane_is_minimum')
    high = frozen['regions']['high']
    pa = tuple(map(Q, high['source_point_exact_m']))
    pb = tuple(map(Q, high['reference_point_exact_m']))
    need(pa in points and pb == (pa[0], pa[1], Q(1)) and pb[2] - pa[2] == bound, 'frozen_point_attains_independent_bound')
    point_row = vertex_rows[points.index(pa)]
    native_members = [i for i in rows if point_row in faces[i]]
    need(min(native_members) == 49114 and high['distance_exact_m'] == str(bound), 'canonical_native_point_face')
    highest = max(p[2] for p in points)
    attaining_faces = [i for i in rows if any(Q(world[v][2]) == highest for v in faces[i])]
    need(min(attaining_faces) == 49114, 'global_canonical_source_face_for_plane_minimum')
    # The upper-face triangle containing the frozen projected point is native row0.
    face0 = [tuple(map(Q, whole['vertices'][v])) for v in whole['faces'][0]]
    def orient(a,b,p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    signs = [orient(face0[i], face0[(i+1)%3], pb) for i in range(3)]
    need(all(p[2] == 1 for p in face0) and (all(x >= 0 for x in signs) or all(x <= 0 for x in signs)), 'frozen_reference_native_face0')
    return {'status': 'pass', 'source_vertices': len(world), 'source_triangles': len(faces),
            'selected_triangles': len(rows), 'selected_vertices': len(vertex_rows),
            'reference_triangles': len(whole['faces']), 'world_geometry_binary64_exact': True,
            'ordered_native_rows_exact': True, 'original_precision_preserved': True,
            'view_layer_binding': {'current_packet_instance': binding['source_frame']['view_layer'],
                'archived_name': original['source']['view_layer'],
                'archived_instance': original['source']['view_layer_id'],
                'scope': 'separate native processes; complete measured geometry matched directly'},
            'independent_cube_lower_bound_m': str(bound), 'frozen_points_attain_bound': True,
            'frozen_point_native_faces': [49114, 0], 'selected_native_rows_sha256': digest(rows),
            'method': 'independent scalar closed-box rebuild; exact rational closed Cube face coverage and attained lower bound'}
