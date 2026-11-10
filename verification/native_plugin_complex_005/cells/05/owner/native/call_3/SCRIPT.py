import numpy as np
print('units',bpy.context.scene.unit_settings.system,bpy.context.scene.unit_settings.scale_length)
dg=bpy.context.evaluated_depsgraph_get()
def read_geom(obj):
 ev=obj.evaluated_get(dg); mesh=ev.to_mesh()
 try:
  mesh.calc_loop_triangles()
  mat=np.array(ev.matrix_world,dtype=np.float64)
  pts=np.array([v.co[:] for v in mesh.vertices],dtype=np.float64)@mat[:3,:3].T+mat[:3,3]
  tri=np.array([tuple(t.vertices) for t in mesh.loop_triangles],dtype=int)
  edges=np.unique(np.sort(np.concatenate([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1),axis=0)
  return pts,tri,edges
 finally: ev.to_mesh_clear()
geoms={o.name:read_geom(o) for o in meshes}
target=geoms['Target']
for name,(pts,tris,edges) in geoms.items():
 if name=='Target':
  print('Target_bounds',pts.min(0).tolist(),pts.max(0).tolist())
print('evaluated_geometry_ready',len(geoms),'tri_counts',sorted(set(len(g[1]) for g in geoms.values())))