"""Opt-in real Blender regression for image format restoration, no user data."""
import sys
sys.dont_write_bytecode=True
from pathlib import Path
import base64,hashlib,importlib.util,json,time
import bpy

args=sys.argv[sys.argv.index('--')+1:];assert len(args)==2
root,out=map(lambda p:Path(p).resolve(),args);assert out.is_dir()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
 sys.modules[name]=module;spec.loader.exec_module(module);return module
host_module=load('_png_regression_host',root/'human_eye_plugin/blender_host.py')
helper=load('_png_regression_state',root/'human_eye_plugin/episode_gateway.py')
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
signs=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(2,3,7),(2,7,6),(1,2,6),(1,6,5),(3,0,4),(3,4,7)]
for name,size,center,color in [('GreyBase',(.2,.2,.02),(0,0,.01),(.45,.48,.5,1.)),
                             ('BluePart',(.06,.06,.03),(0,0,.039),(.12,.4,.85,1.))]:
 mesh=bpy.data.meshes.new(name+'_mesh');mesh.from_pydata([[s[k]*size[k]/2 for k in range(3)] for s in signs],[],faces)
 obj=bpy.data.objects.new(name,mesh);scene.collection.objects.link(obj);obj.location=center;obj.color=color
 obj.select_set(False)
bpy.context.view_layer.objects.active=None;bpy.context.view_layer.update()
source=out/'new_fixture.blend';assert not source.exists()
bpy.ops.wm.save_as_mainfile(filepath=str(source),check_existing=True)
digest=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
before_sha=digest(source);rows=[]
for profile in ('default_png','initialized_png','exr16','jpeg'):
 for view in ('SCENE','XY','XZ'):
  bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
  scene=bpy.context.scene;image=scene.render.image_settings
  if profile=='initialized_png':image.file_format='PNG'
  if profile=='exr16':image.file_format='OPEN_EXR';image.color_depth='16'
  if profile=='jpeg':image.file_format='JPEG'
  host=host_module.BlenderSceneHost(bpy_module=bpy,execution_metadata=True,identity_metadata=True)
  evidence=host.capture_readonly_evidence();names={m['name']:m['object_id'] for m in evidence['capture']['meshes']}
  state=helper.native_render_state(bpy,scene,bpy.context.view_layer);error=None;raw=None;repeat_equal=None
  try:
   raw=host.observe_readonly_native(profile+'_'+view,names['BluePart'],names['GreyBase'],
    evidence['capture']['revision'],time.perf_counter_ns()+20_000_000_000,view)
   if profile=='default_png':
    host.observe_readonly_native(profile+'_'+view+'_again',names['BluePart'],names['GreyBase'],
     evidence['capture']['revision'],time.perf_counter_ns()+20_000_000_000,view)
    repeat_equal=state==helper.native_render_state(bpy,scene,bpy.context.view_layer)
  except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
  after=helper.native_render_state(bpy,scene,bpy.context.view_layer)
  png=base64.b64decode(raw['overview']['image_base64'],validate=True) if raw else b''
  rows.append({'profile':profile,'view':view,'error':error,'image_returned':raw is not None,
   'full_state_equal':state==after,'repeat_full_state_equal':repeat_equal,
   'geometry_equal':host.capture_readonly_evidence()==evidence,
   'empty_name_before':state['image_color_management']['linear_colorspace_settings']['name']=='',
   'empty_name_after':after['image_color_management']['linear_colorspace_settings']['name']=='',
   'format_before':state['image_settings']['file_format'],'format_after':after['image_settings']['file_format'],
   'png_384':png[:8]==b'\x89PNG\r\n\x1a\n' and png[16:24]==b'\x00\x00\x01\x80\x00\x00\x01\x80',
   'writer_stores_absent':all(k not in bpy.app.driver_namespace for k in (
    '_human_eye_owned_episode_gateway_v1','_human_eye_forward_deadline_requirements_v1','_human_eye_motion_ledger_v1'))})
value={'passed':all(r['error'] is None and r['image_returned'] and r['full_state_equal'] and r['geometry_equal']
 and r['writer_stores_absent'] and r['png_384'] for r in rows),'rows':rows,
 'input_SHA_unchanged':digest(source)==before_sha,'episode_helper_sha256':digest(root/'human_eye_plugin/episode_gateway.py')}
with (out/'RESULT.json').open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2)
print(json.dumps({'passed':value['passed'],'cases':len(rows)}))
raise SystemExit(not value['passed'])
