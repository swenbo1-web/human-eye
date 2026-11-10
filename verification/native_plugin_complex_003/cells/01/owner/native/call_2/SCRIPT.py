import bpy, numpy as np, math
from mathutils import Vector
from mathutils.bvhtree import BVHTree
objs={}
for name in ['Object_01','Object_02','Object_03','Object_04']:
 o=bpy.data.objects.get(name)
 if o is None:
  print(name,'MISSING'); continue
 dg=bpy.context.evaluated_depsgraph_get(); eo=o.evaluated_get(dg); me=eo.to_mesh(); me.calc_loop_triangles()
 verts=np.array([tuple(eo.matrix_world @ v.co) for v in me.vertices],dtype=float)
 tris=np.array([tuple(t.vertices) for t in me.loop_triangles],dtype=int)
 objs[name]={'v':verts,'t':tris}
 print(name,'type',o.type,'vertices',len(verts),'triangles',len(tris),'matrix', [list(r) for r in eo.matrix_world],'bounds',verts.min(0).tolist(),verts.max(0).tolist())
 print('local vertices', [tuple(v.co) for v in me.vertices] if len(verts)<40 else 'omitted')
 print('triangles',tris.tolist() if len(tris)<70 else 'omitted')
 eo.to_mesh_clear()
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)