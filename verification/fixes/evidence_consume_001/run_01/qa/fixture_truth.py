"""Assignment-derived fixture geometry and raw-readback checks; no product imports."""
from collections import Counter
from fractions import Fraction as F


NAMES = ('Object_01', 'Object_02')
IDENTITY = [[1., 0., 0., 0.], [0., 1., 0., 0.],
            [0., 0., 1., 0.], [0., 0., 0., 1.]]
QUESTIONS = {
    'S': '当前 Object_01 与 Object_02 的三角表面最小距离是多少米？给出从前者到后者的单位方向，以及两者各自的边界边数和非流形边数。',
    'G': '报告当前两对象的最小表面距离、最近点方向，以及实体穿插状态。区分有数值答案、不适用和当前无法判定的项目，并说明原因。',
}


def grid_faces(ni, nj):
    """i is the outer row, j inner; every cell uses its low-low/high-high diagonal."""
    result = []
    for i in range(ni - 1):
        for j in range(nj - 1):
            a, b = i * nj + j, (i + 1) * nj + j
            c, d = (i + 1) * nj + j + 1, i * nj + j + 1
            result.extend(([a, b, c], [a, c, d]))
    return result


def exact_vertices(case, index):
    if case == 'S':
        n, u, v = (2, -1, 2), (1, 2, 0), (-4, 2, 5)
        rows = []
        for i in range(4):
            for j in range(3):
                point = [F(i*u[k] + j*v[k], 32) for k in range(3)]
                if index == 0 and i == 3:
                    point = [point[k] - F(n[k], 64) for k in range(3)]
                if index == 1:
                    point = [point[k] + F(n[k], 32) for k in range(3)]
                    if i == 3:
                        point = [point[k] + F(n[k], 64) for k in range(3)]
                rows.append(point)
        return rows
    if case == 'G':
        return [[F(s, 16), F(s, 16), F(t, 16)] if index == 0 else
                [F(s+t, 16), F(s-t, 16), F(0)]
                for s in range(-2, 3) for t in range(-2, 3)]
    raise ValueError('Unknown fixed fixture')


def expected_geometry(case):
    faces = grid_faces(4, 3) if case == 'S' else grid_faces(5, 5)
    return {name: dict(vertices=[[float(value) for value in point]
                                for point in exact_vertices(case, index)],
                       faces=faces, matrix=IDENTITY, modifiers=0)
            for index, name in enumerate(NAMES)}


def topology(faces):
    incidence = Counter(tuple(sorted((face[k], face[(k+1) % 3])))
                        for face in faces for k in range(3))
    return dict(boundary_edge_count=sum(value == 1 for value in incidence.values()),
                nonmanifold_edge_count=sum(value > 2 for value in incidence.values()))


def validate_readback(case, actual):
    expected = expected_geometry(case)
    if actual != expected:
        raise ValueError('fixture_raw_readback_differs_from_assignment_' + case)
    for index, name in enumerate(NAMES):
        mesh = actual[name]
        exact = exact_vertices(case, index)
        if [[F(value) for value in point] for point in mesh['vertices']] != exact:
            raise ValueError('fixture_binary32_coordinates_not_exact_' + case)
        for face in mesh['faces']:
            a, b, c = (exact[k] for k in face)
            u = [b[k]-a[k] for k in range(3)]
            v = [c[k]-a[k] for k in range(3)]
            cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2],
                     u[0]*v[1]-u[1]*v[0]]
            if not any(cross):
                raise ValueError('fixture_degenerate_triangle_' + case)
        counts = topology(mesh['faces'])
        if counts != dict(boundary_edge_count=10 if case == 'S' else 16,
                          nonmanifold_edge_count=0):
            raise ValueError('fixture_topology_differs_from_assignment_' + case)
        if case == 'S':
            dots = [2*point[0]-point[1]+2*point[2] for point in exact]
            if index == 0 and not all(value <= 0 for value in dots):
                raise ValueError('S_A_support_halfspace')
            if index == 1 and not all(value >= F(9, 32) for value in dots):
                raise ValueError('S_B_support_halfspace')
        if case == 'G':
            if index == 0 and not all(point[0] == point[1] for point in exact):
                raise ValueError('G_A_plane')
            if index == 1 and not all(point[2] == 0 for point in exact):
                raise ValueError('G_B_plane')
            if [F(0), F(0), F(0)] not in exact:
                raise ValueError('G_common_original_surface_vertex')
    return dict(case=case, assignment_geometry_exact=True, binary32_coordinates_exact=True,
                object_count=2, vertices_per_mesh=12 if case == 'S' else 25,
                triangles_per_mesh=12 if case == 'S' else 32,
                boundary_edges_per_mesh=10 if case == 'S' else 16,
                nonmanifold_edges_per_mesh=0, product_solver_calls=0)
