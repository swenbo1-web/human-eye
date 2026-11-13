import bpy
print([(o.name,len(o.data.polygons)) for o in bpy.context.scene.objects if o.type=='MESH'])