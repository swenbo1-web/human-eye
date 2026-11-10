"""Read actual saved .blend evaluated geometry in a fresh Blender process."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import bpy

p = argparse.ArgumentParser()
p.add_argument('--output',required=True)
args = p.parse_args(sys.argv[sys.argv.index('--')+1:])
source = Path(bpy.data.filepath).resolve()
assert source.is_file()
scene = bpy.context.scene
depsgraph = bpy.context.evaluated_depsgraph_get()
rows = []
for obj in sorted(scene.objects,key=lambda obj:obj.name):
    assert obj.type == 'MESH'
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=depsgraph)
    try:
        mesh.calc_loop_triangles()
        matrix = evaluated.matrix_world
        rows.append({'name':obj.name,'type':obj.type,'parent':None if obj.parent is None else obj.parent.name,
            'modifiers':[modifier.type for modifier in obj.modifiers],
            'matrix_world':[[float(v) for v in row] for row in matrix],
            'vertices_local':[[float(v) for v in vertex.co] for vertex in mesh.vertices],
            'vertices_world_native':[[float(v) for v in matrix@vertex.co] for vertex in mesh.vertices],
            'triangles':[list(triangle.vertices) for triangle in mesh.loop_triangles],
            'source_polygon_count':len(mesh.polygons),
            'source_polygon_sizes':[len(face.vertices) for face in mesh.polygons]})
    finally:
        evaluated.to_mesh_clear()
out = {'schema':'m1-independent-evaluated-mesh-v1','source_asset':str(source),
    'source_asset_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
    'blender_version':bpy.app.version_string,'unit_scale_m':scene.unit_settings.scale_length,
    'saved_frame':scene.frame_current,'objects':rows}
with Path(args.output).open('x',encoding='utf8') as stream:
    json.dump(out,stream,sort_keys=True,indent=2,allow_nan=False)
    stream.write('\n')
print(json.dumps({'exported_objects':len(rows),'saved_asset':str(source),'output':args.output}))
