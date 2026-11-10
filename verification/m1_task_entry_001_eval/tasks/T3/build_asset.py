"""Construct only this task's new frozen fixture; no product imports."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import random
import sys
import bpy
from mathutils import Matrix


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def ears(poly):
    remaining = list(range(len(poly)))
    out = []
    while len(remaining) > 3:
        for j, b in enumerate(remaining):
            a, c = remaining[j-1], remaining[(j+1) % len(remaining)]
            if cross(poly[a], poly[b], poly[c]) <= 0:
                continue
            if any(all(cross(poly[u], poly[v], poly[p]) >= 0
                for u, v in ((a, b), (b, c), (c, a)))
                for p in remaining if p not in (a, b, c)):
                continue
            out.append((a, b, c))
            remaining.pop(j)
            break
        else:
            raise ValueError('frozen polygon ear construction failed')
    return out+[tuple(remaining)]


def box(low, high):
    x, y, z = low
    X, Y, Z = high
    vertices = [(x,y,z),(X,y,z),(X,Y,z),(x,Y,z),(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)]
    faces = [(0,3,2),(0,2,1),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
        (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return vertices, faces


def refine(vertices, faces):
    vertices = list(vertices)
    lookup = {v:i for i,v in enumerate(vertices)}
    def midpoint(a, b):
        point = tuple((x+y)/2 for x,y in zip(vertices[a],vertices[b]))
        if point not in lookup:
            lookup[point] = len(vertices)
            vertices.append(point)
        return lookup[point]
    out = []
    for a,b,c in faces:
        ab,bc,ca = midpoint(a,b),midpoint(b,c),midpoint(c,a)
        out.extend(((a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)))
    return vertices,out


def geometry(spec, role):
    scale = F(spec['construction_scale_m'])
    if spec['task'] == 'T2':
        if role == 'target':
            poly = [tuple(F(x) for x in p) for p in spec['polygon_base']]
            vertices = [(x*scale,y*scale,z*scale) for z in (-1,1) for x,y in poly]
            n = len(poly)
            faces = [tuple(reversed(face)) for face in ears(poly)]
            faces += [tuple(i+n for i in face) for face in ears(poly)]
            for i in range(n):
                j = (i+1) % n
                faces += [(i,j,j+n),(i,j+n,i+n)]
            return refine(vertices, faces)
        low, high = spec['candidate_boxes_base'][role]
        return box(tuple(F(v)*scale for v in low), tuple(F(v)*scale for v in high))
    delta, length = F(spec['gap_m']), scale
    xs = [F(x)*scale for x in spec['ribbon_grid_base']]
    layers = [F(x)*scale for x in spec['ribbon_layers_base']]
    heights = [F(x)*scale for x in spec['ribbon_heights_base']]
    vertices = []
    for layer,height in zip(layers,heights):
        for along in xs:
            if role == 'target': point = (along,-layer,-height)
            elif role == 'cross': point = (layer,along,delta+height)
            elif role == 'right': point = (length+delta/2+layer,along,delta+height)
            elif role == 'left': point = (-length-3*delta/4-layer,along,delta+height)
            elif role == 'front': point = (along,delta/2+layer,delta+height)
            elif role == 'upper': point = (layer,along,3*delta/2+height)
            else: raise ValueError('unexpected frozen role')
            vertices.append(point)
    faces = []
    n = len(xs)
    for j in range(len(layers)-1):
        for i in range(n-1):
            a,b,c,d = j*n+i,j*n+i+1,(j+1)*n+i+1,(j+1)*n+i
            faces += [(a,b,c),(a,c,d)]
    return vertices,faces


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--spec',required=True)
    p.add_argument('--output',required=True)
    args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
    spec = json.loads(Path(args.spec).read_bytes())
    output = Path(args.output).resolve()
    assert not output.exists()
    output.parent.mkdir(parents=True,exist_ok=True)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'METERS'
    scene.unit_settings.scale_length = 1.0
    for role in spec['creation_order']:
        vertices,faces = geometry(spec,role)
        bounds = [(min(v[k] for v in vertices),max(v[k] for v in vertices)) for k in range(3)]
        origin = tuple((low+high)/2 for low,high in bounds)
        rng = random.Random(spec['seed'] ^ int(hashlib.sha256(role.encode()).hexdigest()[:8],16))
        order = list(range(len(vertices)))
        rng.shuffle(order)
        remap = {old:new for new,old in enumerate(order)}
        local = [tuple(float(v-origin[k]) for k,v in enumerate(vertices[i])) for i in order]
        faces = [tuple(remap[i] for i in face) for face in faces]
        rng.shuffle(faces)
        name = spec['object_names'][role]
        mesh = bpy.data.meshes.new(name+'_mesh')
        mesh.from_pydata(local,[],faces)
        mesh.update()
        obj = bpy.data.objects.new(name,mesh)
        scene.collection.objects.link(obj)
        obj.matrix_world = Matrix.Translation(tuple(float(x) for x in origin))
        obj.color = (0.5,0.5,0.5,1.0)
    bpy.context.view_layer.update()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output),check_existing=False)
    print(json.dumps({'saved_new_asset':str(output),'objects':len(scene.objects),'task':spec['task']}))


if __name__ == '__main__': main()
