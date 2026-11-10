cache={}
for n,o in objs.items():
 me=o.data; me.calc_loop_triangles()
 vs=np.array([tuple(v.co) for v in me.vertices],dtype=float)
 mw=np.array(o.matrix_world,dtype=float); w=vs@mw[:3,:3].T+mw[:3,3]
 ts=np.array([tuple(t.vertices) for t in me.loop_triangles],dtype=int)
 cache[n]={'v':w,'t':ts,'local':vs,'matrix':mw}
 print(n,'local vertices',vs.tolist(),'world AABB',w.min(axis=0).tolist(),w.max(axis=0).tolist())
 print('triangles',ts.tolist())