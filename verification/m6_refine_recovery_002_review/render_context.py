"""Render current real geometry for choosing a reference-driven local task."""
import argparse
from pathlib import Path
import sys
import bpy
from mathutils import Vector

parser=argparse.ArgumentParser()
parser.add_argument('--output-directory',required=True)
options=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
out=Path(options.output_directory);out.mkdir(parents=True,exist_ok=True)
target=bpy.data.objects['0135bbc4-c6c7-4003-a402-6f2e0283497d']
for obj in bpy.context.scene.objects:
    if obj.type=='MESH':obj.hide_render=(obj!=target)
scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO'
scene.display.shading.color_type='SINGLE'
scene.display.shading.single_color=(.65,.65,.65)
scene.display.shading.background_type='WORLD'
scene.world.color=(.8,.8,.8)
scene.display.shading.show_shadows=True
scene.display.shading.show_cavity=True
scene.render.image_settings.file_format='PNG'
camera_data=bpy.data.cameras.new('independent_context_camera')
camera=bpy.data.objects.new('independent_context_camera',camera_data)
scene.collection.objects.link(camera);scene.camera=camera
camera_data.type='ORTHO'
views=[('whole_front',(2,0,.5),(0,0,.5),1.07,480,800),
       ('forearm_front',(2,.155,.565),(0,.155,.565),.285,640,640),
       ('forearm_side',(0,2,.565),(0,.155,.565),.285,640,640)]
for name,location,center,scale,width,height in views:
    camera.location=location
    camera.rotation_euler=(Vector(center)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.ortho_scale=scale
    scene.render.resolution_x=width;scene.render.resolution_y=height
    scene.render.resolution_percentage=100
    scene.render.filepath=str(out/(name+'.png'))
    bpy.ops.render.render(write_still=True)
print('context_views_rendered',len(views))
