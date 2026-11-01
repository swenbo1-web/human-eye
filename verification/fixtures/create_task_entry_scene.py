"""Owned factory fixture for zero-motion admission; no external scene input."""
from pathlib import Path
import sys,bpy
path=Path(sys.argv[sys.argv.index('--')+1]).resolve()
assert path.name=='fixture.blend' and path.parent.name.startswith('he-entry-') and not path.exists()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.unit_settings.system='METRIC';bpy.context.scene.unit_settings.scale_length=1.
signs=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(3,7,6),(3,6,2),(0,4,7),(0,7,3),(1,2,6),(1,6,5)]
for name,size,z in [('GreyBase',(.2,.2,.2),0.),('BluePart',(.1,.1,.1),.154)]:
    mesh=bpy.data.meshes.new(name+'_mesh');mesh.from_pydata([[s[k]*size[k]/2 for k in range(3)] for s in signs],[],faces);mesh.update()
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);obj.location.z=z
    obj.select_set(name=='BluePart')
    if name=='BluePart':bpy.context.view_layer.objects.active=obj
bpy.context.view_layer.update();bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=True)
assert path.is_file()
