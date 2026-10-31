"""Run deterministic routing acceptance in an open Blender, then restore it.

Load with runpy.run_path(...); call run_live_test(project_root, engine_python).
No model calls, add-on installation, saving, or edits to preexisting objects.
"""
from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time
import uuid


def _load(root, name, filename):
    spec=importlib.util.spec_from_file_location(name,root/'human_eye_plugin'/filename)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def run_live_test(project_root, engine_python):
    import bpy
    from mathutils import Matrix
    root=Path(project_root).resolve()
    out=root/'verification/fixes/20261022_blender_host/live'
    out.mkdir(parents=True,exist_ok=True)
    host_module=_load(root,'human_eye_live_host','blender_host.py')
    process_module=_load(root,'human_eye_live_router','router_process.py')
    original_scene=bpy.context.scene
    window=bpy.context.window
    if window is None:
        raise RuntimeError('This acceptance requires an open Blender window')
    original_objects={o.name: [list(row) for row in o.matrix_world] for o in original_scene.objects}
    original_selection=sorted(o.name for o in original_scene.objects if o.select_get())
    original_active=bpy.context.view_layer.objects.active
    original_active_name=original_active.name if original_active else None
    name='HumanEye_Routing_Test_'+uuid.uuid4().hex[:8]
    test_scene=bpy.data.scenes.new(name)
    created_objects=[]
    created_meshes=[]
    checks=[]
    report={'kind':'live_blender_deterministic_host_acceptance','blender_version':bpy.app.version_string,
            'model_calls':0,'test_scene':name,'original_scene':original_scene.name,
            'original_file_saved':False,'tests':checks}
    router=None
    timings=[]
    report['engine_calls']=timings
    def check(label, condition, **facts):
        checks.append({'test':label,'passed':bool(condition),**facts})
        if not condition:raise AssertionError(label+': '+str(facts))
    def create_box(label,center,size,color):
        signs=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
               (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
        faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(2,3,7,6),(1,2,6,5),(3,0,4,7)]
        mesh=bpy.data.meshes.new(name+'_'+label+'_mesh')
        mesh.from_pydata([[s[k]*size[k]/2 for k in range(3)] for s in signs],[],faces)
        mesh.update()
        obj=bpy.data.objects.new(name+'_'+label,mesh)
        test_scene.collection.objects.link(obj)
        obj.matrix_world=Matrix.Translation(center)
        obj.color=(*color,1)
        created_objects.append(obj);created_meshes.append(mesh)
        return obj
    try:
        window.scene=test_scene
        test_scene.unit_settings.system='METRIC'
        test_scene.unit_settings.scale_length=1.0
        base=create_box('base',(0,0,.1),(1.4,1.2,.2),(.3,.5,.7))
        part=create_box('part',(0,0,.35),(.3,.2,.1),(.8,.5,.2))
        obstacle=create_box('obstacle',(.8,0,.35),(.2,.2,.2),(.8,.2,.2))
        part.select_set(True)
        bpy.context.view_layer.objects.active=part
        host=host_module.BlenderSceneHost()
        focal_id=host.object_id(part);reference_id=host.object_id(base)
        router=process_module.ExternalRouterProcess(engine_python,root,
                                                   readback_atol_m=1e-6,quad_size=384)
        sid='live:'+name
        task='Inspect the three-dimensional scene and measure the part/base clearance.'
        event={'event':'before_model','session_id':sid,'task_kind':'spatial_3d',
               'task_instruction':task,'focal_id':focal_id,'reference_id':reference_id}
        def route(event):
            started=time.perf_counter()
            result=router.handle_event(event)
            timings.append({'event':event['event'],'elapsed_ms':round((time.perf_counter()-started)*1000,3),
                            'route':result['route'],'cache_hit':result['cache_hit']})
            return result
        def observe(label):
            snapshot=host.capture_scene()
            result=route({**event,'scene':snapshot})
            check(label,result['route']=='engine' and result['measurement_valid'] and result['axes_valid'],
                  route=result['route'],reasons=result['reason_codes'])
            return result,snapshot
        def gate(obs,action,snapshot=None):
            return route({'event':'before_action','session_id':sid,
                'scene':snapshot or host.capture_scene(),'observation_id':obs['observation_id'],
                'focal_id':focal_id,'reference_id':reference_id,'action':action})
        def accepted_apply(obs,action,label):
            decision=gate(obs,action)
            check(label+'_gate',decision['allow_action'] is True,reasons=decision['reason_codes'])
            result=host.apply_transform({**action,'focal_id':focal_id,'reference_id':reference_id},
                                       expected_revision=decision['scene_revision'],
                                       expected_fingerprint=decision['scene_fingerprint'])
            actual=host.capture_scene()
            post=route({**event,'event':'after_action','scene':actual})
            check(label+'_actual_host_readback',post['route']=='engine' and not post['requires_reobserve'],
                  reasons=post['reason_codes'],receipt=result['receipt'])
            return post,actual
        obs,before=observe('automatic_observation_before_model')
        facts=json.loads(obs['context_text'])
        check('actual_geometry_clearance',abs(facts['measurement']['signed_clearance_m']-.1)<1e-6,
              clearance_m=facts['measurement']['signed_clearance_m'])
        image_path=out/'live_quad_before.png'
        image_path.write_bytes(base64.b64decode(obs['image']['data'],validate=True))
        report['before_image']=str(image_path)
        original_part=[list(row) for row in part.matrix_world]
        blocked=gate(obs,{'translation':[0,0,-.15]})
        check('penetrating_action_blocked',blocked['allow_action'] is False and
              blocked['reason_codes']==['candidate_collision'],reasons=blocked['reason_codes'])
        check('blocked_action_did_not_mutate_host',[list(row) for row in part.matrix_world]==original_part)
        blocked=gate(obs,{'translation':[.8,0,0]})
        check('third_object_collision_blocked',blocked['allow_action'] is False and
              blocked['reason_codes']==['candidate_collision'],reasons=blocked['reason_codes'])
        part.location.x += .02
        bpy.context.view_layer.update()
        stale=gate(obs,{'translation':[0,0,.01]})
        check('external_scene_edit_invalidates_observation',stale['allow_action'] is False and
              stale['reason_codes']==['stale_or_missing_observation'],reasons=stale['reason_codes'])
        obs,_=observe('reobserve_changed_live_scene')
        post,actual=accepted_apply(obs,{'translation':[0,0,.05],
                                      'rotation_euler_deg':[0,0,12]},'translation_and_rotation')
        after_path=out/'live_quad_after.png'
        after_path.write_bytes(base64.b64decode(post['image']['data'],validate=True))
        report['after_image']=str(after_path)
        facts=json.loads(post['context_text'])
        check('final_clearance_from_actual_vertices',abs(facts['measurement']['signed_clearance_m']-.15)<1e-6,
              clearance_m=facts['measurement']['signed_clearance_m'])
        # Metres remain consistent when Blender unit settings use centimetres.
        test_scene.unit_settings.scale_length=.01
        obs,scaled=observe('scene_unit_scale_converted_to_metres')
        facts=json.loads(obs['context_text'])
        check('centimetre_scene_measurement',abs(facts['measurement']['signed_clearance_m']-.0015)<1e-7,
              clearance_m=facts['measurement']['signed_clearance_m'])
        post,_=accepted_apply(obs,{'translation':[0,0,.002]},'world_metre_delta_in_centimetre_scene')
        actual_gap=json.loads(post['context_text'])['measurement']['signed_clearance_m']
        check('unit_aware_host_readback',abs(actual_gap-.0035)<1e-7,clearance_m=actual_gap)
        test_scene.unit_settings.scale_length=1.0
        obs,_=observe('restore_metre_scene_for_full_rotation')
        accepted_apply(obs,{'translation':[.01,-.02,.03],
                            'rotation_euler_deg':[3,-4,9]},'full_xyz_rotation')
        report['all_passed']=True
    except Exception as exc:
        report['all_passed']=False
        report['error']=type(exc).__name__+': '+str(exc)
    finally:
        if router is not None:router.close()
        window.scene=original_scene
        for obj in created_objects:
            bpy.data.objects.remove(obj,do_unlink=True)
        for mesh in created_meshes:
            if mesh.users==0:bpy.data.meshes.remove(mesh)
        bpy.data.scenes.remove(test_scene)
        unchanged=all(o.name in original_objects and [list(row) for row in o.matrix_world]==original_objects[o.name]
                      for o in original_scene.objects) and len(original_scene.objects)==len(original_objects)
        restored_selection=sorted(o.name for o in original_scene.objects if o.select_get())
        active=bpy.context.view_layer.objects.active
        restored_active=active.name if active else None
        report['original_scene_restored']=bpy.context.scene.name==original_scene.name
        report['original_objects_unchanged']=unchanged
        report['original_selection_unchanged']=restored_selection==original_selection and restored_active==original_active_name
        report['test_scene_removed']=name not in bpy.data.scenes
        report['all_passed']=bool(report.get('all_passed') and unchanged and report['original_scene_restored']
                                  and report['original_selection_unchanged'] and report['test_scene_removed'])
        report['report_path']=str(out/'live_acceptance.json')
        (out/'live_acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report
