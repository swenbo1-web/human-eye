"""Build the fixed surface-only QA assets without consulting product kernels."""
import argparse
import bpy
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys


parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True, type=Path)
parser.add_argument('--reuse-g', required=True, type=Path)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
root = args.root.resolve()
faces = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
         (2,3,7),(2,7,6),(1,2,6),(1,6,5),(3,0,4),(3,4,7)]
signs = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
         (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2)


def add(name, vertices, triangles):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(vertices, [], triangles)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    assert [list(vertex.co) for vertex in mesh.vertices] == [list(vertex) for vertex in vertices]
    return obj


def readback():
    return {obj.name: dict(vertices=[list(vertex.co) for vertex in obj.data.vertices],
        faces=[list(face.vertices) for face in obj.data.polygons],
        matrix=[list(row) for row in obj.matrix_world], modifiers=len(obj.modifiers))
        for obj in bpy.data.objects if obj.type == 'MESH'}


g = root / 'author/G'
g.mkdir(parents=True, exist_ok=False)
for filename in ('scene.blend', 'BUILD_READBACK.json'):
    source = args.reuse_g / filename
    target = g / filename
    shutil.copyfile(source, target)
    assert source.read_bytes() == target.read_bytes()
previous = json.loads((g / 'BUILD_READBACK.json').read_text(encoding='utf8'))
u, v = (1/8,-1/8,0), (1/16,1/16,-1/8)
corners = [tuple(s*u[k] + t*v[k] for k in range(3)) for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
assert previous['Object_01']['vertices'] == [list(point) for point in corners]
assert previous['Object_02']['vertices'] == [[point[k]+1/64 for k in range(3)] for point in corners]
changed = [[point[k]-1/64 for k in range(3)] for point in corners]
save(g / 'qa_patch.json', dict(target_name='Object_01',
    vertices=[dict(index=index, co=point) for index,point in enumerate(changed)]))
save(g / 'TRUTH.json', dict(schema='surface-facts-independent-qa-v1', solver_calls=0,
    source_asset=str(args.reuse_g / 'scene.blend'),
    source_asset_sha256=hashlib.sha256((args.reuse_g/'scene.blend').read_bytes()).hexdigest(),
    method='Parallel exact dyadic planes; centres attain their Euclidean plane-distance lower bound',
    states={
        'initial':dict(objects=['Object_01','Object_02'], distance_m=math.sqrt(3)/64,
            exact_squared_distance='3/4096', direction_a_to_b=[1/math.sqrt(3)]*3,
            witnesses=[[0,0,0],[1/64]*3], boundary_edges=[4,4], nonmanifold_edges=[0,0]),
        'changed':dict(objects=['Object_01','Object_02'], distance_m=math.sqrt(3)/32,
            exact_squared_distance='3/1024', direction_a_to_b=[1/math.sqrt(3)]*3,
            witnesses=[[-1/64]*3,[1/64]*3], boundary_edges=[4,4], nonmanifold_edges=[0,0])},
    changed_target_vertices=changed, actual_float32_vertices_exact=True))

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 1
add('Edge_A', [(-2,-2,0),(2,-2,0),(0,2,0)], [(0,1,2)])
add('Edge_B', [(0,0,-1),(0,0,1),(0,1,1)], [(0,1,2)])
add('Closed_A', [(8 + sx/16,sy/16,sz/16) for sx,sy,sz in signs], faces)
add('Closed_B', [(8 + 3/16 + sx/16,sy/16,sz/16) for sx,sy,sz in signs], faces)
control = root / 'author/control'
control.mkdir(parents=True, exist_ok=False)
save(control / 'BUILD_READBACK.json', readback())
bpy.ops.wm.save_as_mainfile(filepath=str(control / 'scene.blend'))
save(control / 'TRUTH.json', dict(schema='surface-facts-independent-qa-v1', solver_calls=0,
    states={
        'edge_crossing':dict(objects=['Edge_A','Edge_B'],distance_m=0,
            exact_squared_distance='0', direction_a_to_b=None, witnesses=[[0,0,0],[0,0,0]],
            boundary_edges=[3,3],nonmanifold_edges=[0,0],
            proof='The B edge from z=-1 to z=1 crosses the A interior at the origin'),
        'closed_separated':dict(objects=['Closed_A','Closed_B'],distance_m=1/16,
            exact_squared_distance='1/256',direction_a_to_b=[1,0,0],
            witnesses=[[8+1/16,0,0],[8+1/8,0,0]],boundary_edges=[0,0],nonmanifold_edges=[0,0],
            proof='Positive X supporting-plane gap 1/16, attained at the face centres')},
    actual_float32_vertices_exact=True))
print(json.dumps(dict(status='assets_built', assets=['G','control'], product_solver_calls=0)))
