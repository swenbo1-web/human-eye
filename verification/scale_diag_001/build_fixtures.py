"""Owned disposable Blender fixtures, exported before any timed sampling."""
import json, math, sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon

HERE = Path(__file__).resolve().parent
OUT = HERE / 'fixtures'

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n', encoding='utf8', newline='\n')

def comb(k, gap=None):
    h, tooth, top = .05, .02, .07
    poly = [(0., 0.), (1., 0.), (1., h)]
    for i in reversed(range(k)):
        a, b = (i+.2)/k, (i+.8)/k
        poly.extend([(b,h),(b,h+tooth),(a,h+tooth),(a,h)])
    poly.append((0.,h))
    n = len(poly)
    vv = [Vector((x,y,0.)) for x,y in poly]
    lookup = {(float(v.x),float(v.y)):i for i,v in enumerate(vv)}
    caps = [[int(v) if isinstance(v,int) else lookup[(float(v.x),float(v.y))] for v in tri] for tri in tessellate_polygon([vv])]
    assert len(caps) == n-2
    vertices = [(x,y,z) for z in (-.05,.05) for x,y in poly]
    faces = [[a,c,b] for a,b,c in caps] + [[a+n,b+n,c+n] for a,b,c in caps]
    for i in range(n):
        j = (i+1)%n
        faces.extend([[i,j,j+n],[i,j+n,i+n]])
    if gap is not None:
        vertices = [(x,2*top+gap-y,z) for x,y,z in vertices]
        faces = [list(reversed(t)) for t in faces]
    assert len(vertices) == 8*k+8 and len(faces) == 16*k+12
    return vertices,faces

def common_matrix():
    return Matrix.Translation((.21,-.33,.17)) @ Matrix.Rotation(math.radians(37),4,'Z') @ Matrix.Rotation(math.radians(19),4,'X')

def snapshot(sid):
    objects = []
    for o in sorted(bpy.context.scene.objects,key=lambda o:o.name):
        if o.type != 'MESH':
            continue
        local = [[float(v) for v in p.co] for p in o.data.vertices]
        mat = [[float(v) for v in row] for row in o.matrix_world]
        world = [[sum(mat[j][i]*p[i] for i in range(3))+mat[j][3] for j in range(3)] for p in local]
        objects.append(dict(logical_id=o['scale_logical_id'],name=o.name,vertices_local=local,vertices_world=world,
                            matrix_world=mat,triangles=[list(p.vertices) for p in o.data.polygons]))
    return dict(id=sid,target_id='target',peer_id='peer',unit_scale_m=float(bpy.context.scene.unit_settings.scale_length),objects=objects)

def make(sid,k,count):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system='METRIC'
    bpy.context.scene.unit_settings.scale_length=1.
    common=common_matrix()
    for i in range(count):
        logical = 'target' if i==0 else 'peer' if i==1 else 'competitor' if i==2 else 'distractor_%03d'%i
        name = 'Target' if i==0 else 'Peer_000' if i==1 else 'Competing_001' if i==2 else 'Near_%03d'%i
        ki = k if i<2 else 3
        gap = None if i==0 else .003 if i==1 else .005 if i==2 else .012 + (i-3)*.001
        vertices,faces=comb(ki,gap)
        mesh=bpy.data.meshes.new(name+'_mesh');mesh.from_pydata(vertices,[],faces);mesh.update()
        obj=bpy.data.objects.new(name,mesh);bpy.context.collection.objects.link(obj);obj['scale_logical_id']=logical
        # Nearest witness falls in face interiors: no aligned vertex shortcut.
        offset=(0.,0.,0.) if i==0 else (.013,0.,.007) if i==1 else (.8,0.,.007) if i==2 else (((i%7)-3)*.011,0.,((i%5)-2)*.009)
        obj.matrix_world=common @ Matrix.Translation(offset)
    bpy.context.view_layer.update()
    path=OUT/(sid+'.blend');bpy.ops.wm.save_as_mainfile(filepath=str(path))
    dump(OUT/(sid+'.json'),snapshot(sid))
    return path

def advance(step):
    if step==1:
        pass
    elif step==2:
        bpy.data.objects['Peer_000'].name='Peer_Renamed'
    elif step==3:
        o=bpy.data.objects['Competing_001']
        o.matrix_world=common_matrix() @ Matrix.Translation((.8,-.004,.007))
    elif step==4:
        o=bpy.data.objects['Competing_001']
        idx=max(range(len(o.data.vertices)),key=lambda i:(o.data.vertices[i].co.x,o.data.vertices[i].co.y,o.data.vertices[i].co.z))
        o.data.vertices[idx].co.z+=.004
        o.data.update()
    elif step==5:
        bpy.data.objects.remove(bpy.data.objects['Competing_001'],do_unlink=True)
    elif step==6:
        bpy.ops.wm.open_mainfile(filepath=str(OUT/'D48.blend'))
    else:
        raise ValueError('step')
    bpy.context.view_layer.update()

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    assert not any(OUT.iterdir()), 'fixture outputs already exist'
    for sid,k,count in [('G60_D12',3,12),('G508',31,12),('G4092',255,12),('D48',3,48),('D192',3,192)]:
        make(sid,k,count)
    bpy.ops.wm.open_mainfile(filepath=str(OUT/'D48.blend'))
    for step in range(7):
        if step:advance(step)
        dump(OUT/('T%d.json'%step),snapshot('T%d'%step))
    dump(OUT/'BUILD_COMPLETE.json',{'blender':bpy.app.version_string,'static_snapshots':5,'T_states':7})
