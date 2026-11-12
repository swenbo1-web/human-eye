import bpy, numpy as np, math, time
scene=bpy.context.scene
depsgraph=bpy.context.evaluated_depsgraph_get()
print('units',scene.unit_settings.system,scene.unit_settings.scale_length)
print('objects',[(ob.name,ob.type,ob.hide_viewport,ob.hide_render) for ob in scene.objects])
