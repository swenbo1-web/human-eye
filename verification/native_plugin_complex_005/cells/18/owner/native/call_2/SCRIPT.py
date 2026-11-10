import bpy
print([(o.name,o.type,len(o.data.vertices) if o.type=='MESH' else None,len(o.data.polygons) if o.type=='MESH' else None) for o in bpy.context.scene.objects])