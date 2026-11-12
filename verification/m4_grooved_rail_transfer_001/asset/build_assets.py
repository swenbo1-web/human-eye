"""Build the one frozen private assembly in a factory background Blender."""

import hashlib
import json
import os
from fractions import Fraction as F
from pathlib import Path
import sys
import time

import bpy
from mathutils import Matrix


HERE = Path(__file__).resolve().parent
ASSET = HERE / 'grooved_rail.blend'


def save(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def determinant(a, b, c):
    return (a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0]))


def tetrahedron_faces(points):
    vectors = [[points[i][j] - points[0][j] for j in range(3)] for i in (1, 2, 3)]
    delta = determinant(*vectors)
    assert delta != 0
    faces = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]
    return faces if delta > 0 else [tuple(reversed(face)) for face in faces]


def frozen_geometry():
    contour = [(F(x), F(z)) for x, z in [
        ('0', '0'), ('40', '0'), ('22.4', '13.2'), ('14', '2'),
        ('1.2', '11.6'), ('9.6', '22.8'), ('0', '30')]]
    target = [(x, F(y), z) for y in (-20, 20) for x, z in contour]
    cap = [(0, 1, 3), (1, 2, 3), (0, 3, 4), (0, 4, 6), (4, 5, 6)]
    target_faces = cap + [tuple(i + 7 for i in reversed(face)) for face in cap]
    for i in range(7):
        j = (i + 1) % 7
        target_faces += [(i, i + 7, j + 7), (i, j + 7, j)]
    a_syh = [(F(s), F(y), F(h)) for s, y, h in [
        ('2', '2', '15.25'), ('0', '-2', '20.25'),
        ('4', '-2', '20.25'), ('2', '8', '20.25')]]
    a = [((4 * s + 3 * h) / 5, y, (-3 * s + 4 * h) / 5) for s, y, h in a_syh]
    normal, tangent = (F(-3, 5), F(0), F(-4, 5)), (F(4, 5), F(0), F(-3, 5))
    p = (F(0), F(5), F(0))
    q = tuple(p[i] + F('2.75') * normal[i] for i in range(3))
    b = [tuple(q[i] + sign * 6 * tangent[i] for i in range(3)) for sign in (1, -1)]
    b += [tuple(q[i] + 8 * normal[i] + (sign * 6 if i == 1 else 0)
                for i in range(3)) for sign in (1, -1)]
    c = [tuple(F(value) for value in point) for point in
         [(10, '28.5', 2), (16, '36.5', -2), (4, '36.5', -2), (10, '36.5', 10)]]
    return [('Target', target, target_faces),
            ('Part_A', a, tetrahedron_faces(a)),
            ('Part_B', b, tetrahedron_faces(b)),
            ('Part_C', c, tetrahedron_faces(c))]


def main():
    started = time.perf_counter_ns()
    assert not ASSET.exists(), 'unique_asset_already_exists'
    assert not (HERE / 'BUILD_RESULT.json').exists()
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for material in list(bpy.data.materials):
        bpy.data.materials.remove(material)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'METERS'
    scene.unit_settings.scale_length = 1.0
    r = [[-10, 2, 11], [10, -5, 10], [5, 14, 2]]
    translation = [120, -80, 240]
    matrix = Matrix([[float(F(r[row][col], 15000)) for col in range(3)]
                     + [float(F(translation[row], 1000))] for row in range(3)]
                    + [[0, 0, 0, 1]])
    construction = []
    for name, points, faces in frozen_geometry():
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata([tuple(float(x) for x in point) for point in points], [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        scene.collection.objects.link(obj)
        obj.rotation_mode = 'QUATERNION'
        obj.matrix_world = matrix.copy()
        construction.append({'name': name, 'vertices_exact_local_mm': [[str(x) for x in p] for p in points],
                             'triangles': [list(face) for face in faces]})
    bpy.context.view_layer.update()
    assert len(bpy.data.objects) == 4
    assert sum(len(o.data.vertices) for o in bpy.data.objects) == 26
    assert sum(len(o.data.polygons) for o in bpy.data.objects) == 36
    assert all(len(p.vertices) == 3 for o in bpy.data.objects for p in o.data.polygons)
    assert all(not o.modifiers and o.animation_data is None and o.parent is None for o in bpy.data.objects)
    assert all(not o.data.materials and not o.keys() and not o.data.keys() for o in bpy.data.objects)
    bpy.ops.wm.save_as_mainfile(filepath=str(ASSET), check_existing=False, compress=False)
    assert ASSET.is_file()
    result = {'schema': 'm4-grooved-rail-build-v1', 'pid': os.getpid(),
              'started_ns': started, 'ended_ns': time.perf_counter_ns(),
              'asset': str(ASSET), 'asset_sha256': sha(ASSET),
              'actual_construction_counts': {'objects': 4, 'vertices': 26, 'triangles': 36},
              'frozen_construction': construction,
              'matrix_world_input_binary32': [list(row) for row in matrix],
              'representation': 'mesh local millimetres; linear R/1000 and translation T/1000; scene scale_length 1',
              'blender_version': bpy.app.version_string,
              'images': 0, 'product_processes': 0, 'model_consumers': 0}
    save(HERE / 'BUILD_RESULT.json', result)
    print(json.dumps({'asset_created': str(ASSET), 'sha256': result['asset_sha256'], 'pid': os.getpid()}))


if __name__ == '__main__':
    main()
