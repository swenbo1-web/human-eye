from pathlib import Path
import importlib.util,json,time,sys
root=Path('D:/he_m4_source_region_live_bounds_qualification_001')
prior=Path('C:/Users/Administrator/.codex/worktrees/m4-target-002/hefe/verification/m4_source_region_live_bounds_qualification_001')
sys.path.insert(0,str(prior))
import replay_rna
spec=importlib.util.spec_from_file_location('scoped_host',Path(sys.argv[1]).resolve(strict=True))
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._READONLY_LOADED_HOST_SHA256='a'*64
cases=json.loads((root/'REQUESTS.json').read_bytes())['cases']
for label,case in cases.items():
 bpy=replay_rna.archive_as_bpy(json.loads(Path(case['terminal']['path']).read_bytes()))
 host=module.BlenderSceneHost(bpy,identity_metadata=True)
 events={o.name:[] for o in bpy.context.scene.objects}
 for o in bpy.context.scene.objects:
  ev=o.evaluated_get(bpy.context.view_layer.depsgraph)
  def spy(operation,event,name):
   def run():
    events[name].append(event)
    return operation()
   return run
  ev.to_mesh=spy(ev.to_mesh,'expand',o.name)
  ev.to_mesh_clear=spy(ev.to_mesh_clear,'clear',o.name)
  ev.data.calc_loop_triangles=spy(ev.data.calc_loop_triangles,'triangulate',o.name)
 for old in case['closed_cases']:
  q=old['query']
  try:
   packet=host.capture_source_region_visual({'target':q['region']['object'], 'reference':q['reference'], 'world_box_m':q['region']['world_box_m']},time.perf_counter_ns()+10**10,64*1024*1024)
  except module.BlenderHostError as e:
   assert label=='ASSEMBLY' and str(e).startswith('source_region_visual_unsupported_static_source:'),str(e)
   assert all(not v for v in events.values())
   print(label,old['label'],str(e).split(':')[0], 'no to_mesh')
   continue
  assert label=='RAIL'
  assert old['original_kept_ordinals']==packet['retained_ordinals']
  assert packet['source_triangle_indices']==old['source_triangle_indices']
  assert module._digest(packet['camera_plan'])==module._digest(old['old_camera_specification'])
  expanded=[row['name'] for row in packet['directory'] if row['ordinal'] in packet['retained_ordinals']]
  assert all(e==(['expand','triangulate','clear'] if n in expanded else []) for n,e in events.items())
  print(label,old['label'],{x:packet['work'][x] for x in ('source_objects','retained_objects','omitted_vertices_checked','omitted_polygons_checked','to_mesh','sent_vertices','sent_triangles')})
  for e in events.values():e.clear()
case=cases['RAIL']
q=next(x['query'] for x in case['closed_cases'] if x['label']=='M21')
request={'target':q['region']['object'],'reference':q['reference'],'world_box_m':q['region']['world_box_m']}
def new():
 bpy=replay_rna.archive_as_bpy(json.loads(Path(case['terminal']['path']).read_bytes()))
 host=module.BlenderSceneHost(bpy,identity_metadata=True)
 return bpy,host
def run(host, budget=64*1024*1024, deadline=None):
 if deadline is None: deadline=time.perf_counter_ns()+10**10
 return host.capture_source_region_visual(request,deadline,budget)
def reject(host, expected, **opts):
 try:run(host,**opts)
 except ValueError as e:
  assert str(e).startswith(expected),(expected,str(e))
 else:raise AssertionError(expected)
 print(expected,'rejected')
bpy,host=new()
base=run(host)
far_row=next(row for row in base['directory'] if row['ordinal'] not in base['retained_ordinals'])
def far_eval(bpy):
 obj=next(o for o in bpy.context.scene.objects if o.name==far_row['name'])
 ev=obj.evaluated_get(bpy.context.view_layer.depsgraph)
 ev.to_mesh=lambda: (_ for _ in ()).throw(AssertionError('far mesh expansion must not occur'))
 return ev
bpy,host=new()
ev=far_eval(bpy)
ev.data.vertices[-1].co=(float('nan'),*ev.data.vertices[-1].co[1:])
reject(host,'source_region_visual_nonfinite_vertex')
bpy,host=new()
ev=far_eval(bpy)
ev.data.loops[-1].vertex_index=len(ev.data.vertices)
reject(host,'acquisition_invalid_triangle_indices')
bpy,host=new()
ev=far_eval(bpy)
ev.data.polygons[-1].loop_start=0
reject(host,'source_region_visual_irregular_loop_layout')
bpy,host=new()
ev=far_eval(bpy)
ev.data.vertices[-1].co=(ev.data.vertices[-1].co[0]+10,*ev.data.vertices[-1].co[1:])
reject(host,'source_region_visual_rna_bound_disagrees')
bpy,host=new()
reject(host,'source_region_visual_document_budget_exceeded',budget=1)
bpy,host=new()
reject(host,'source_region_visual_deadline_exceeded',deadline=time.perf_counter_ns()-1)
from copy import deepcopy
cam=deepcopy(base['camera_plan'])
# Identity views with strict X outside and a Y path which overflows.
for pose in cam['views']:
 pose['view_matrix']=[[1.,0.,0.,0.],[0.,1.e308,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
 pose['projection_matrix']=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
assert module._observation_outside_xy_viewports([[2.,10.,0.],[3.,11.,0.]],cam)[0]
assert not module._source_region_visual_outside_xy_viewports([[2.,10.,0.],[3.,11.,0.]],cam)[0]
print('legacy X early / later Y overflow kept by private proof')
for pose in cam['views']:
 pose['view_matrix'][1][1]=1.
assert not module._source_region_visual_outside_xy_viewports([[1.,0.,0.],[2.,0.,0.]],cam)[0]
assert module._source_region_visual_outside_xy_viewports([[1.01,0.,0.],[2.,0.,0.]],cam)[0]
assert not module._source_region_visual_outside_xy_viewports(None,cam)[0]
print('touch and unknown kept; finite clear gap excluded')
