validate_code('import bpy\nprint(len(bpy.context.scene.objects))')
_consumer_scope_state['running'] = True
try:
    exec(compile('import bpy\nprint(len(bpy.context.scene.objects))', '<ordinary-blender-task>', 'exec'), _ordinary_blender_namespace)
finally:
    _consumer_scope_state['running'] = False
