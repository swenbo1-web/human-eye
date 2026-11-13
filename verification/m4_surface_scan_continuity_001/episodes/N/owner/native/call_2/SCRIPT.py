assert '_human_eye_continuity_marker' not in globals()
_human_eye_continuity_marker = {'marker_token':'continuity-engineering-N-001','marker_generation':1}
import json as _continuity_json, os as _continuity_os
_continuity_marker = globals()['_human_eye_continuity_marker']
print(_continuity_json.dumps({**_continuity_marker, 'pid':_continuity_os.getpid(),
'namespace_id':id(globals()), 'unit_scale':float(bpy.context.scene.unit_settings.scale_length),
'objects':[{'name':obj.name,'session_uid':int(obj.session_uid),
'matrix_world':[[float(x) for x in row] for row in obj.matrix_world]}
for obj in sorted(bpy.context.scene.objects,key=lambda obj:obj.name) if obj.type=='MESH']},allow_nan=False))
