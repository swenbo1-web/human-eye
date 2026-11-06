import json
ob=bpy.data.objects['Object_01']
print(json.dumps({'target_local_vertices':[list(v.co) for v in ob.data.vertices], 'rotation_euler':[float(x) for x in ob.rotation_euler], 'scale':list(ob.scale), 'target_bounds':[[min(v.co[i] for v in ob.data.vertices),max(v.co[i] for v in ob.data.vertices)] for i in range(3)]}))
