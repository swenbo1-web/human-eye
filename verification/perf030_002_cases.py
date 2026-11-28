"""Finite PT cases and exact rational expectations for PERF-030-002.

The source is prepared before the CPU window. No probes run at import time.
"""
from __future__ import annotations

from fractions import Fraction
import numpy as np

from verification.test_concave_geometry import box, entity


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def _subtract(left, right):
    return [a - b for a, b in zip(left, right)]


def triangle_truth(point, triangle):
    """Exact constrained PT minimum for the represented binary64 inputs."""
    point = [Fraction(float(value)) for value in point]
    a, b, c = [[Fraction(float(value)) for value in row] for row in triangle]
    ab, ac, offset = _subtract(b, a), _subtract(c, a), _subtract(point, a)
    aa, cc, bc = _dot(ab, ab), _dot(ac, ac), _dot(ab, ac)
    determinant = aa * cc - bc * bc
    if determinant <= 0:
        raise ValueError('Exact oracle requires a nondegenerate triangle')
    dab, dac = _dot(offset, ab), _dot(offset, ac)
    u = (dab * cc - dac * bc) / determinant
    v = (dac * aa - dab * bc) / determinant
    values = []
    if u >= 0 and v >= 0 and u + v <= 1:
        residual = [offset[k] - u * ab[k] - v * ac[k] for k in range(3)]
        values.append(_dot(residual, residual))
    for start, end in ((a, b), (b, c), (c, a)):
        delta, shift = _subtract(end, start), _subtract(point, start)
        parameter = max(Fraction(0), min(Fraction(1), _dot(shift, delta) / _dot(delta, delta)))
        residual = [shift[k] - parameter * delta[k] for k in range(3)]
        values.append(_dot(residual, residual))
    return {'distance_sq': min(values), 'u': u, 'v': v,
            'inside': u >= 0 and v >= 0 and u + v <= 1}


def leaf_cases():
    """Two dispatched probes plus eight preregistered deterministic variants."""
    h = 2.0 ** -30
    triangle = np.array([[0., 0, 0], [1., 0, 0], [1., h, 0]])
    point = np.array([2., h, 1.])
    values = [('primary_nonzero', point, triangle),
              ('primary_false_zero', np.array([2., 0, 0]), triangle)]
    for exponent in (-24, -38):
        height = 2.0 ** exponent
        tri = np.array([[0., 0, 0], [1., 0, 0], [1., height, 0]])
        values.append((f'height_2pow{exponent}', np.array([2., height, 1.]), tri))
    rotation = np.array([[1., 2, -2], [2., 1, 2], [2., -2, -1]]) / 3
    values.append(('rotated_represented', point @ rotation.T, triangle @ rotation.T))
    far = np.array([.75, h / 2, 2.0 ** 20])
    values.append(('rotated_far_normal', far @ rotation.T, triangle @ rotation.T))
    values.append(('inside_edge', np.array([1 - 2.0 ** -30, h / 2, 0]), triangle))
    values.append(('outside_below_collision_tolerance', np.array([1 + 2.0 ** -30, h / 2, 0]), triangle))
    values.append(('outside_above_collision_tolerance', np.array([1 + 2.0 ** -29, h / 2, 0]), triangle))
    shift = np.full(3, 2.0 ** 22)
    values.append(('large_translation_representable_thin_axis', point + shift, triangle + shift))
    return [{'name': name, 'point': point, 'triangle': tri} for name, point, tri in values]


def closed_counterexample():
    """The single dispatched closed wrapper, with its original face order."""
    left = box((2.5, .5, .5), (1, 1, 1), 'a')
    parts = [box((1.5, 3 * j + .25, -.25), (.5, .5, .5), 'part') for j in range(6)]
    h = 2.0 ** -30
    vertices = np.array([[0, 0, 0], [1, 0, 0], [1, h, 0],
                         [0, 0, -1], [1, 0, -1], [1, h, -1]], dtype=float)
    faces = np.array([[0, 1, 2], [3, 5, 4], [0, 3, 4], [0, 4, 1],
                      [1, 4, 5], [1, 5, 2], [2, 5, 3], [2, 3, 0]])
    parts.append(entity('prism', vertices, faces))
    offsets = np.cumsum([0] + [len(part.vertices) for part in parts[:-1]])
    right = entity('b', np.vstack([part.vertices for part in parts]),
                   np.vstack([part.faces + offset for part, offset in zip(parts, offsets)]))
    return left, right


def task_response(pair, cache):
    """Return the whole task response and separate diagnostic counters."""
    from human_eye_plugin.task_query import task_result
    scene = {'revision': 'perf030-002-fixed', 'unit': 'm', 'coordinate_frame': 'world',
             'source': 'perf030_002_fixed_meshes', 'meshes': [mesh.to_dict() for mesh in pair]}
    query = {'mode': 'task', 'objects': [{'id': mesh.object_id} for mesh in pair],
             'requested_facts': ['surface_clearance', 'solid_relation', 'nearest_witness']}
    diagnostics = {}
    response = task_result(scene, pair, 'perf030-002-fixed-fingerprint', query, cache,
                           lambda _: None, diagnostics=diagnostics)
    return response, diagnostics
