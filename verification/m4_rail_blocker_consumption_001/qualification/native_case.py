"""Independent LEFT overlap check executed in the ordinary live tool."""

from fractions import Fraction
from itertools import pairwise
import json


def clip(points, axis, boundary, sign):
    if not points:
        return []
    kept = []
    for a, b in pairwise([points[-1], *points]):
        value_a = sign * (a[axis] - boundary)
        value_b = sign * (b[axis] - boundary)
        if (value_a >= 0) != (value_b >= 0):
            t = value_a / (value_a - value_b)
            kept.append(tuple(x + t * (y - x) for x, y in zip(a, b)))
        if value_b >= 0:
            kept.append(b)
    return kept


def check_left(targets):
    capture = scene_data()
    meshes = {
        obj['name']: (tuple(tuple(map(Fraction, p)) for p in obj['vertices']), obj['triangles'])
        for obj in capture['objects'] if obj['visible_get']
    }
    counts = {
        'objects': len(meshes), 'vertices': sum(len(vertices) for vertices, _ in meshes.values()),
        'triangles': sum(len(triangles) for _, triangles in meshes.values()),
    }
    results = []
    for name, source_indices in targets:
        vertices, triangles = meshes[name]
        target = [vertices[i] for face in source_indices for i in triangles[face]]
        x, = {p[0] for p in target}
        (y0, y1), (z0, z1) = [(min(p[i] for p in target), max(p[i] for p in target)) for i in (1, 2)]
        hits = []
        for candidate, (verts, faces) in meshes.items():
            for face_index, face in enumerate(faces):
                xyz = [verts[i] for i in face]
                if min(p[0] for p in xyz) >= x:
                    continue
                # LEFT travels along (-1, 0, 1). Its rays preserve y and x+z.
                polygon = [(u, v, w) for u, v, w in xyz]
                front = clip(polygon, 0, x, -1)
                polygon = [(v, u + w - x) for u, v, w in front]
                for axis, bound, sign in ((0, y0, 1), (0, y1, -1), (1, z0, 1), (1, z1, -1)):
                    polygon = clip(polygon, axis, bound, sign)
                if len(polygon) < 3:
                    continue
                twice_area = sum(a[0] * b[1] - b[0] * a[1] for a, b in pairwise([polygon[-1], *polygon]))
                if twice_area:
                    hits.append([candidate, face_index, str(abs(twice_area) / 2)])
        results.append({'target': [name, source_indices], 'view': 'LEFT', 'hits': sorted(hits)})
    print(json.dumps({'source_ref': capture['source_ref'], 'counts': counts, 'targets': results},
                     separators=(',', ':')))


check_left(TARGETS)
