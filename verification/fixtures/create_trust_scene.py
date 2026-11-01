"""Create a new isolated acceptance fixture, never load or save user scenes."""
from pathlib import Path
import math
import sys
import bpy

target=Path(sys.argv[sys.argv.index('--')+1]).resolve()
assert target.name=='fixture.blend' and target.parent.name.startswith('he-trust-')
assert not target.exists()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.unit_settings.system='METRIC'
bpy.context.scene.unit_settings.scale_length=1.
signs=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
       (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (2,3,7),(2,7,6),(1,2,6),(1,6,5),(3,0,4),(3,4,7)]
angle=math.radians(10.)
normal=[math.sin(angle),0.,math.cos(angle)]
for name,size,distance in [('GreyBase',(.2,.2,.2),0.),('BluePart',(.06,.06,.1),.154)]:
    mesh=bpy.data.meshes.new(name+'_mesh')
    mesh.from_pydata([[s[k]*size[k]/2 for k in range(3)] for s in signs],[],faces)
    mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location=[normal[k]*distance for k in range(3)]
    obj.rotation_euler[1]=angle
    obj.select_set(name=='BluePart')
    if name=='BluePart':bpy.context.view_layer.objects.active=obj
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(target),check_existing=True)
assert target.is_file()
