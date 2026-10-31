"""Disposable UI scene for testing external hooks/MCP against live Blender."""
from pathlib import Path
import importlib.util
import json
import sys
import uuid

KEY='human_eye_live_connector_acceptance'


def setup(project_root):
    import bpy
    from mathutils import Matrix
    if KEY in bpy.app.driver_namespace:
        raise RuntimeError('An earlier live acceptance needs cleanup first')
    root=Path(project_root);window=bpy.context.window
    if window is None:raise RuntimeError('An open Blender window is required')
    original=window.scene
    saved={'original':original,'original_matrices':{o.name:[list(r) for r in o.matrix_world] for o in original.objects},
           'selection':sorted(o.name for o in original.objects if o.select_get()),
           'active':getattr(bpy.context.view_layer.objects.active,'name',None),'objects':[],'meshes':[]}
    bpy.app.driver_namespace[KEY]=saved
    prefix='HumanEye_Codex_Test_'+uuid.uuid4().hex[:8]
    scene=bpy.data.scenes.new(prefix);saved['test_scene']=scene;window.scene=scene
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1
    def box(label,center,size):
        signs=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
        faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(2,3,7,6),(1,2,6,5),(3,0,4,7)]
        data=bpy.data.meshes.new(prefix+'_'+label+'_mesh')
        data.from_pydata([[s[i]*size[i]/2 for i in range(3)] for s in signs],[],faces);data.update()
        obj=bpy.data.objects.new(prefix+'_'+label,data);scene.collection.objects.link(obj)
        obj.matrix_world=Matrix.Translation(center);saved['objects'].append(obj);saved['meshes'].append(data)
        return obj
    base=box('base',(0,0,.1),(1.4,1.2,.2));part=box('part',(0,0,.35),(.3,.2,.1))
    box('obstacle',(.8,0,.35),(.2,.2,.2))
    part.select_set(True);bpy.context.view_layer.objects.active=part
    source=root/'human_eye_plugin/blender_host.py'
    spec=importlib.util.spec_from_file_location('human_eye_codex_fixture_host',source)
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    manifest={'kind':'disposable_live_blender_fixture','blender_version':bpy.app.version_string,
              'scene_name':scene.name,'focal_id':module.BlenderSceneHost.object_id(part),
              'reference_id':module.BlenderSceneHost.object_id(base),'focal_name':part.name,'reference_name':base.name}
    destination=root/'verification/fixes/20261022_live_hooks/live_fixture.json'
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def cleanup(project_root):
    import bpy
    saved=bpy.app.driver_namespace.pop(KEY)
    bpy.context.window.scene=saved['original']
    test_name=saved['test_scene'].name
    for obj in saved['objects']:bpy.data.objects.remove(obj,do_unlink=True)
    for mesh in saved['meshes']:
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    bpy.data.scenes.remove(saved['test_scene'])
    scene=saved['original']
    matrices={o.name:[list(r) for r in o.matrix_world] for o in scene.objects}
    result={'original_scene_restored':bpy.context.scene==scene,
            'original_objects_unchanged':matrices==saved['original_matrices'],
            'original_selection_unchanged':sorted(o.name for o in scene.objects if o.select_get())==saved['selection'],
            'original_active_unchanged':getattr(bpy.context.view_layer.objects.active,'name',None)==saved['active'],
            'test_scene_removed':test_name not in bpy.data.scenes,'file_saved':False}
    path=Path(project_root)/'verification/fixes/20261022_live_hooks/live_cleanup.json'
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
