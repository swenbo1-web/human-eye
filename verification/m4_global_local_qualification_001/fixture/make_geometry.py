"""Emit the one fixed dyadic recipe without importing Blender or the product."""

from fractions import Fraction as F
import json
from pathlib import Path
import struct


HERE = Path(__file__).resolve().parent
IDENTITY = [[int(i == j) for j in range(4)] for i in range(4)]


def rectangle(center, u, v):
    center, u, v = [list(map(F, vector)) for vector in (center, u, v)]
    vertices = [[center[k] + a * u[k] / 2 + b * v[k] / 2 for k in range(3)]
                for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    return vertices, [[0, 1, 2], [0, 2, 3]]


def box(center, u, v, w):
    center, u, v, w = [list(map(F, vector)) for vector in (center, u, v, w)]
    bottom, _ = rectangle([center[k] - w[k] / 2 for k in range(3)], u, v)
    vertices = bottom + [[point[k] + w[k] for k in range(3)] for point in bottom]
    quads = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (3, 7, 6, 2), (1, 2, 6, 5), (0, 4, 7, 3))
    triangles = []
    for a, b, c, d in quads:
        triangles.extend(([a, b, c], [a, c, d]))
    return vertices, triangles


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main():
    ring_vertices = [[F(x), F(y), F(0)] for x, y in
                     ((-16, -16), (16, -16), (16, 16), (-16, 16),
                      (-12, -12), (12, -12), (12, 12), (-12, 12))]
    ring_triangles = []
    for i in range(4):
        j = (i + 1) % 4
        ring_triangles.extend(([i, j, 4 + j], [i, 4 + j, 4 + i]))
    s = F(1, 16)
    l_vertices = [[F(4) + x * s, F(4) + y * s, F(1)]
                  for x, y in ((0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3))]
    recipes = [
        ('rotated_large_box', box((-4, -4, 1), (F(3, 4), 1, 0), (-1, F(3, 4), 0), (0, 0, 2))),
        ('open_horizontal', rectangle((0, 0, 1), (F(1, 8), 0, 0), (0, F(1, 8), 0))),
        ('cover_box', box((2, 2, F(19, 16)), (1, 0, 0), (0, 1, 0), (0, 0, F(1, 8)))),
        ('small_vertical', rectangle((-4, 0, 1), (0, F(1, 8), 0), (0, 0, F(1, 8)))),
        ('open_square_ring', (ring_vertices, ring_triangles)),
        ('covered_horizontal', rectangle((2, 2, 1), (F(1, 8), 0, 0), (0, F(1, 8), 0))),
        ('L_shape', (l_vertices, [[0, i, i + 1] for i in range(1, 5)])),
        ('axis_large_box', box((F(7, 2), F(-7, 2), 1), (1, 0, 0), (0, 1, 0), (0, 0, 2))),
        ('open_inclined', rectangle((-2, 0, 1), (F(1, 8), 0, 0), (0, F(3, 32), F(1, 32)))),
    ]
    objects, roles = [], {}
    for ordinal, (role, (vertices, triangles)) in enumerate(recipes):
        name = 'Obj_' + str(ordinal + 1).zfill(2)
        roles[role] = name
        for point in vertices:
            for value in point:
                if F(struct.unpack('<f', struct.pack('<f', float(value)))[0]) != value:
                    raise ValueError('recipe_not_exact_binary32')
        for triangle in triangles:
            a, b, c = [vertices[index] for index in triangle]
            u, v = [[point[k] - a[k] for k in range(3)] for point in (b, c)]
            cross = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
            if cross == [0, 0, 0]:
                raise ValueError('degenerate_recipe_triangle')
        objects.append(dict(name=name, ordinal=ordinal, matrix_world=IDENTITY,
            vertices_world_m=[[str(value) for value in point] for point in vertices], triangles=triangles))
    counts = dict(objects=len(objects), vertices=sum(len(row['vertices_world_m']) for row in objects),
                  triangles=sum(len(row['triangles']) for row in objects))
    if counts != dict(objects=9, vertices=54, triangles=56):
        raise ValueError('fixed_recipe_counts_changed')
    save(HERE / 'GEOMETRY.json', dict(schema='m4-global-local-geometry-v1',
        coordinate_encoding='exact_rational_strings', unit='metre', scale_length=1,
        frame=1, subframe=0, counts=counts, objects=objects))
    save(HERE / 'private/ROLE_MAP.json', dict(schema='m4-global-local-role-map-v1',
        private_for_oracle_only=True, roles=roles, objects={name: role for role, name in roles.items()},
        controls=dict(local_positive=roles['open_horizontal'], local_negative=roles['covered_horizontal'])))
    task = ('检查当前整个场景。以最大共边、共面且绕序一致的三角连通分量为单位，'
            '找出整体为矩形、面积在 [1/128, 1/32] 平方米之间（含端点）、'
            '带方向单位法向的 z 分量至少为 3/4 的全部区域。\n'
            '报告当前对象、源三角形行号、世界位置、面积和法向，并为每个区域提供实际完整可读的图像见证。'
            '允许使用既有六方向拟合局部视窗。若无法取得见证，分别说明实际遮挡或像素证据不足的具体原因。'
            '只读观察，保持场景及源文件。\n')
    with (HERE / 'TASK.txt').open('x', encoding='utf8', newline='\n') as stream:
        stream.write(task)


if __name__ == '__main__':
    main()
