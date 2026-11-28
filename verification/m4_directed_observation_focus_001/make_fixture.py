"""Generate only a public synthetic fixture in an owned Blender process."""
import json
from pathlib import Path
import sys

import bpy

target = Path(sys.argv[sys.argv.index('--') + 1])
vertices = [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
            (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
faces = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
         (3,7,6),(3,6,2),(0,4,7),(0,7,3),(1,2,6),(1,6,5)]
assert not target.exists()
obj = bpy.data.objects['Cube']
mesh = bpy.data.meshes.new('SourceTriangles')
mesh.from_pydata(vertices, [], faces)
mesh.update()
obj.data = mesh
obj.name = 'Box'
bpy.ops.wm.save_as_mainfile(filepath=str(target))
mesh.calc_loop_triangles()
target.with_suffix('.truth.json').write_text(json.dumps({
    'name': obj.name, 'vertices': [list(v.co) for v in mesh.vertices],
    'faces': [list(t.vertices) for t in mesh.loop_triangles],
    'blender': bpy.app.version_string
}, indent=2), encoding='utf8')
