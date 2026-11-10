import bpy
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
print('mesh_count',len(meshes))
print([(o.name,len(o.data.vertices),len(o.data.polygons)) for o in meshes])
