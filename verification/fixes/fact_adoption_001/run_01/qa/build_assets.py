"""Build the two fixed binary-rational fixtures in one owned Blender process."""
import bpy
import json
import math
from fractions import Fraction
from pathlib import Path
import sys

ROOT = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
FACES = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
         (2,3,7),(2,7,6),(1,2,6),(1,6,5),(3,0,4),(3,4,7)]

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding='utf8')

def clear():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1

def add(name, vertices, faces):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    actual = [list(vertex.co) for vertex in mesh.vertices]
    assert actual == [list(vertex) for vertex in vertices]
    return obj

def readback():
    return {obj.name: dict(vertices=[list(vertex.co) for vertex in obj.data.vertices],
        faces=[list(face.vertices) for face in obj.data.polygons],
        matrix=[list(row) for row in obj.matrix_world], modifiers=len(obj.modifiers))
        for obj in bpy.data.objects if obj.type == 'MESH'}

def vertices(t0, t1):
    return [(3*s - 4*t, 4*s + 3*t, z)
        for z in (-1/16,1/16)
        for s,t in ((-1/8,t0),(1/8,t0),(1/8,t1),(-1/8,t1))]

clear()
a = add('Object_01', vertices(-1/128, 1/128), FACES)
b = add('Object_02', vertices(2/128, 4/128), FACES)
initial = readback()
patch = {'target_name':'Object_01','vertices':[
    {'index':index,'co':list(vertices(-1/128,3/128)[index])} for index in (2,3,6,7)]}
save(ROOT/'author/S/qa_patch.json', patch)
save(ROOT/'author/S/BUILD_READBACK.json', initial)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'author/S/scene.blend'))
low_a = [min(vertex[k] for vertex in initial['Object_01']['vertices']) for k in range(3)]
high_a = [max(vertex[k] for vertex in initial['Object_01']['vertices']) for k in range(3)]
low_b = [min(vertex[k] for vertex in initial['Object_02']['vertices']) for k in range(3)]
high_b = [max(vertex[k] for vertex in initial['Object_02']['vertices']) for k in range(3)]
assert all(max(low_a[k],low_b[k]) < min(high_a[k],high_b[k]) for k in range(3))
for name, expected in (('Object_01',(-1/128,1/128)),('Object_02',(2/128,4/128))):
    ts = [(-4*Fraction(v[0])+3*Fraction(v[1]))/25 for v in initial[name]['vertices']]
    assert min(ts) == Fraction(expected[0]) and max(ts) == Fraction(expected[1])
save(ROOT/'author/S/TRUTH.json', dict(schema='fact-adoption-independent-truth-v1',
    coordinate_unit='m', method='Exact dyadic coefficients and orthogonal basis vectors of length five',
    solver_calls=0, initial=dict(relation='separated',minimum_surface_distance_m=5/128,
        direction_a_to_b=[-.8,.6,0], witnesses=[[ -4/128,3/128,0],[-8/128,6/128,0]],
        proof='Parallel t support planes are 5/128 apart, attained at s=z=0', world_aabb_overlap=True),
    changed=dict(relation='penetrating',shared_strict_interior_point=[-.078125,.05859375,0],
        target_and_candidate_nearest_t_margin_m=5/256, world_aabb_overlap=True,
        proof='Point has t=5/256, s=z=0 and is strictly inside both closed boxes'),
    actual_float32_vertices_exact=True, changed_target_vertices=vertices(-1/128,3/128)))

clear()
u=(1/8,-1/8,0)
v=(1/16,1/16,-2/16)
corners=[tuple(s*u[k]+t*v[k] for k in range(3)) for s,t in ((-1,-1),(1,-1),(1,1),(-1,1))]
offset=(1/64,1/64,1/64)
add('Object_01',corners,[(0,1,2),(0,2,3)])
add('Object_02',[tuple(p[k]+offset[k] for k in range(3)) for p in corners],[(0,1,2),(0,2,3)])
current=readback()
save(ROOT/'author/G/BUILD_READBACK.json',current)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'author/G/scene.blend'))
assert all(sum(Fraction(x) for x in vertex)==0 for vertex in current['Object_01']['vertices'])
assert all(sum(Fraction(x) for x in vertex)==Fraction(3,64) for vertex in current['Object_02']['vertices'])
save(ROOT/'author/G/TRUTH.json',dict(schema='fact-adoption-independent-truth-v1',coordinate_unit='m',
    method='Parallel planes x+y+z=0 and x+y+z=3/64; exact dyadic corners and centre witnesses',
    solver_calls=0, minimum_surface_distance_m=math.sqrt(3)/64,
    direction_a_to_b=[1/math.sqrt(3)]*3,witnesses=[[0,0,0],list(offset)],
    closed_solid_condition=False, boundary_edges_per_mesh=4,
    proof='Plane separation is attained by centres. Four boundary edges have one incident triangle.',
    actual_float32_vertices_exact=True))
print(json.dumps(dict(status='built', assets=['S','G'])))
