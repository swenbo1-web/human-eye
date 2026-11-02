"""Owned QA quaternion component interpolation and source precheck replay.

Factory writes only build independent fixtures. Product calls remain read-only;
these are separate saved static frames, not animation-timeline certification.
"""
import argparse,hashlib,json,math,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'verification/fixes/20261102_safety_source_batch'
VERTICES=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.],[.5,.5,.5]]
TRIANGLES=[[0,1,2],[0,2,3]]
FIRST=[1.,0.,0.,0.];LAST=[.5,0.,0.,math.sqrt(3)/2]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_bytes())
def save(path,value):
 with Path(path).open('x',encoding='utf8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)
def catalog():
 return dict(schema='source-precheck-quaternion-cases-v1',cases=[
  dict(name='linear_frame7',interpolation='LINEAR',frame=7,accepted=True),dict(name='linear_frame13',interpolation='LINEAR',frame=13,accepted=True),
  dict(name='constant_frame13',interpolation='CONSTANT',frame=13,accepted=True),
  dict(name='bezier_frame13',interpolation='BEZIER',frame=13,accepted=False,status='unknown',reason='small_skin_curve_interpolation'),
  dict(name='extra_modifier',interpolation='LINEAR',frame=13,accepted=False,status='unsupported',reason='small_skin_modifier_count'),
  dict(name='DQ',interpolation='LINEAR',frame=13,accepted=False,status='unsupported',reason='small_skin_DQ')],
  original_vertices=VERTICES,triangles=TRIANGLES,quaternion_keys=[dict(frame=1,value=FIRST),dict(frame=25,value=LAST)],
  bone=dict(name='Bone',head=[0.,0.,0.],tail=[0.,1.,0.],roll=0.,rest='identity'),weights='all four vertices Bone=1',
  oracle='raw captured action key component LERP or CONSTANT, independent NumPy axis-angle Rodrigues rotation and full single-bone LBS; independent QR/SVD metrics',
  position_atol=1e-6,metric_atol=1e-9,scope='factory QA only, three accepted static snapshots; no timeline/author asset/production character coverage',product_setters=0,saves_original=False)

def curve_rows(action):return [f for layer in action.layers for strip in layer.strips for bag in strip.channelbags for f in bag.fcurves]

def builder(args):
 import bpy
 assert bpy.app.background and load(args.registration)==catalog()
 assert args.output.is_absolute() and args.output.resolve().is_relative_to(ROOT/'verification/fixes');args.output.mkdir(exist_ok=False)
 rows=[]
 for case in catalog()['cases']:
  bpy.ops.wm.read_factory_settings(use_empty=True)
  scene=bpy.context.scene;scene.unit_settings.scale_length=1.
  arm=bpy.data.armatures.new('RigData');rig=bpy.data.objects.new('Armature',arm);scene.collection.objects.link(rig)
  bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
  bone=arm.edit_bones.new('Bone');bone.head=(0.,0.,0.);bone.tail=(0.,1.,0.);bone.roll=0.;bpy.ops.object.mode_set(mode='OBJECT')
  data=bpy.data.meshes.new('MeshData');data.from_pydata(VERTICES,[],TRIANGLES);data.update()
  mesh=bpy.data.objects.new('Cylinder',data);scene.collection.objects.link(mesh)
  group=mesh.vertex_groups.new(name='Bone');group.add(list(range(len(VERTICES))),1.,'REPLACE')
  mod=mesh.modifiers.new('Armature','ARMATURE');mod.object=rig;mod.use_bone_envelopes=False;mod.use_deform_preserve_volume=False;mod.use_vertex_groups=True
  pose=rig.pose.bones['Bone'];pose.rotation_mode='QUATERNION'
  for frame,value in ((1,FIRST),(25,LAST)):
   pose.rotation_quaternion=value;pose.keyframe_insert(data_path='rotation_quaternion',frame=frame,group='Bone')
  action=rig.animation_data.action;action.name='QuaternionAction'
  for curve in curve_rows(action):
   curve.extrapolation='CONSTANT'
   for key in curve.keyframe_points:key.interpolation=case['interpolation']
  if case['name']=='extra_modifier':mesh.modifiers.new('UnsupportedSubdivision','SUBSURF').levels=6
  if case['name']=='DQ':mod.use_deform_preserve_volume=True
  scene.frame_set(case['frame']);bpy.context.view_layer.update()
  folder=args.output/case['name'];folder.mkdir();scene_path=folder/'fixture.blend'
  bpy.ops.wm.save_as_mainfile(filepath=str(scene_path),check_existing=True)
  row=dict(case,scene=str(scene_path),scene_sha256=sha(scene_path))
  rows.append(row)
  save(folder/'AUTHORED_RNA.json',dict(frame=scene.frame_current,pose_quaternion=list(pose.rotation_quaternion),rest_matrix=[list(row) for row in arm.bones['Bone'].matrix_local],
   key_curves=[dict(path=f.data_path,index=f.array_index,keys=[dict(co=list(k.co),interpolation=k.interpolation) for k in f.keyframe_points]) for f in curve_rows(action)],QA_creation_only=True))
 save(args.output/'CASES.json',dict(rows=rows,registration_sha256=sha(args.registration),builder_sha256=sha(Path(__file__)),factory_QA_only=True,source_author_assets_changed=False))
 print(json.dumps(dict(built=len(rows),accepted=3,unsupported=3,QA_creation_only=True)))

def raw_component_values(curves,frame,interpolation):
 import numpy as np
 assert len(curves)==4 and {f['array_index'] for f in curves}==set(range(4))
 q=[]
 for index in range(4):
  curve=next(f for f in curves if f['array_index']==index)
  assert curve['data_path']=='pose.bones["Bone"].rotation_quaternion'
  points=curve['keys'];assert len(points)==2 and [float(k['co'][0]) for k in points]==[1.,25.]
  assert points[0]['interpolation']==points[1]['interpolation']==interpolation
  np.testing.assert_allclose([points[0]['co'][1],points[1]['co'][1]],[FIRST[index],LAST[index]],atol=2e-7,rtol=0.)
  a,b=[float(k['co'][1]) for k in points];q.append(a if interpolation=='CONSTANT' else a+(b-a)*(frame-1)/24)
 return np.asarray(q,dtype=float)

def quaternion_rotation(values):
 """Independent axis/angle Rodrigues calculation, not production polynomial."""
 import numpy as np
 q=np.asarray(values,dtype=float);q=q/np.linalg.norm(q);w=q[0];v=q[1:];length=np.linalg.norm(v)
 if length==0:return np.eye(3)
 axis=v/length;angle=2*math.atan2(length,w);x,y,z=axis
 cross=np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])
 return np.eye(3)*math.cos(angle)+(1-math.cos(angle))*np.outer(axis,axis)+math.sin(angle)*cross

def independent_metrics(original,current):
 import numpy as np
 a=np.asarray(original);b=np.asarray(current);old=(a[1:]-a[0]).T;new=(b[1:]-b[0]).T
 _q,upper=np.linalg.qr(old,mode='reduced');mapping=np.linalg.solve(upper.T,new.T).T
 return np.linalg.svd(mapping,compute_uv=False),float(np.linalg.norm(np.cross(new[:,0],new[:,1]))/np.linalg.norm(np.cross(old[:,0],old[:,1])))

def verify(packet,report,case):
 import numpy as np
 raw=packet['inputs'];bones=raw['rig']['bones'];mesh=raw['mesh'];evaluated=packet['evaluated']
 assert raw['frame']==dict(number=case['frame'],subframe=0.) and raw['unit_scale_m']==1.
 assert mesh['vertices']==VERTICES and mesh['triangles']==TRIANGLES and mesh['groups']==['Bone'] and mesh['weights']==[[[0,1.]] for _ in VERTICES]
 assert len(bones)==1 and bones[0]['name']=='Bone' and bones[0]['rotation_mode']=='QUATERNION'
 np.testing.assert_allclose(bones[0]['rest_matrix'],np.eye(4),atol=1e-7,rtol=0.)
 assert len(raw['actions'])==1
 curves=[f for layer in raw['actions'][0]['layers'] for strip in layer['strips'] for bag in strip['channelbags'] for f in bag['fcurves']]
 channels=raw_component_values(curves,case['frame'],case['interpolation']);rotation=quaternion_rotation(channels)
 np.testing.assert_allclose(bones[0]['rotation_quaternion'],channels,atol=2e-7,rtol=0.)
 expected=(rotation@np.asarray(VERTICES).T).T;actual=np.asarray(evaluated['vertices']);error=float(np.max(np.abs(expected-actual)))
 assert error<=1e-6,error
 np.testing.assert_allclose(np.asarray(bones[0]['pose_matrix'])[:3,:3],rotation,atol=1e-6,rtol=0.)
 assert report['triangles_total']==2 and report['triangles_measured']==2 and report['triangles_unknown']==report['triangles_collapsed']==0
 assert report['execution_authority'] is False and report['geometry_setters']==0 and report['original_file_saved'] is False and report['damage_classification']=='not_inferred'
 assert report['source_validation']['animation_curves_checked']==4 and len(report['triangles'])==2
 for row in report['triangles']:
  tri=TRIANGLES[row['triangle']];stretches,area=independent_metrics([VERTICES[i] for i in tri],[evaluated['vertices'][i] for i in tri])
  np.testing.assert_allclose(row['principal_stretches'],stretches,atol=1e-9,rtol=0.);assert abs(row['area_ratio']-area)<1e-9
  np.testing.assert_allclose(stretches,[1.,1.],atol=1e-6,rtol=0.);assert abs(area-1.)<1e-6
 return dict(passed=True,frame=case['frame'],interpolation=case['interpolation'],raw_component_quaternion=channels.tolist(),rotation_matrix=rotation.tolist(),max_vertex_error=error,
  vertices_checked=4,triangles_checked=2,animation_curves_checked=4,not_timeline_certification=True)

def controller(args):
 sys.path.insert(0,str(args.core_root.resolve()))
 if args.entry:
  import importlib.util
  spec=importlib.util.spec_from_file_location('_source_precheck_target',args.entry.with_name('target_runtime_entry.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  proof=module.validate_binding(expected_python=sys.executable);assert Path(proof['module_root'])==args.core_root.resolve();module.verify_imported_runtime(proof)
 from human_eye_plugin.runtime_identity import runtime_identity,check_source_drift
 identity=runtime_identity();assert check_source_drift()['compatible'] and load(args.registration)==catalog()
 fixtures=load(args.fixtures/'CASES.json');assert fixtures['registration_sha256']==sha(args.registration) and fixtures['builder_sha256']==sha(Path(__file__))
 args.output.mkdir(exist_ok=False);rows=[];binary=Path('D:/Tools/blender5.2/blender.exe')
 for case in fixtures['rows']:
  folder=args.output/case['name'];folder.mkdir();profile=dict(schema='small-skin-source-operator-profile-v1',blender_executable=str(binary),blender_sha256=sha(binary),scene_file=case['scene'],scene_sha256=case['scene_sha256'],
   mesh_name='Cylinder',rig_name='Armature',expected_frame=dict(number=case['frame'],subframe=0.),unit_scale_m=1.,runtime_source_sha256=identity['source_sha256'])
  save(folder/'PROFILE.json',profile)
  cmd=[sys.executable,*(['-I'] if args.entry else []),'-B',*([str(args.entry)] if args.entry else ['-m','human_eye_plugin.small_skin_source_process']),
   '--operator-profile',str(folder/'PROFILE.json'),'--output',str(folder/'readback')]
  started=time.perf_counter_ns();result=subprocess.run(cmd,cwd=ROOT,input=b'',stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=40);elapsed=time.perf_counter_ns()-started
  (folder/'STDOUT.bin').write_bytes(result.stdout);(folder/'STDERR.bin').write_bytes(result.stderr)
  save(folder/'EXECUTION.json',dict(command=cmd,actual_subprocess=True,exit_code=result.returncode,complete_wall_ns=elapsed,stdout_sha256=sha(folder/'STDOUT.bin'),process_reaped=True))
  if case['accepted']:
   assert result.returncode==0,result.stdout.decode('utf8','replace')
   packet=load(folder/'readback/SNAPSHOTS.json')['second'];report=load(folder/'readback/REPORT.json');checked=verify(packet,report,case)
   assert report['source']['runtime_source_sha256']==identity['source_sha256']
   save(folder/'INDEPENDENT.json',checked)
   row=dict(case=case['name'],passed=True,accepted=True,**{k:checked[k] for k in ('max_vertex_error','vertices_checked','triangles_checked','animation_curves_checked')})
  else:
   assert result.returncode==1,result.stdout.decode('utf8','replace');failure=load(folder/'readback/FAILURE.json')
   assert failure['reason']==case['reason'] and failure['status']==case['status'],failure
   assert not (folder/'readback/REPORT.json').exists() and not failure['execution_authority'] and failure['geometry_setters']==0
   row=dict(case=case['name'],passed=True,accepted=False,error=failure)
  assert sha(case['scene'])==case['scene_sha256']
  row.update(original_file_unchanged=True,geometry_setters=0,process_reaped=True,complete_wall_ns=elapsed);save(folder/'RESULT.json',row);rows.append(row)
 summary=dict(all_passed=True,total=len(rows),cases=rows,runtime_source_sha256=identity['source_sha256'],runtime_count=len(identity['source_files']),
  harness_sha256=sha(Path(__file__)),source_or_installed='installed' if args.entry else 'source',QA_only=True,formal_model_comparisons=0,not_timeline_certification=True)
 save(args.output/'RESULT.json',summary);print(json.dumps(summary))

if __name__=='__main__':
 parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--preregister',action='store_true');mode.add_argument('--builder',action='store_true');mode.add_argument('--controller',action='store_true')
 parser.add_argument('--registration',type=Path,default=EVIDENCE/'SOURCE_PRECHECK_CASES_PREREGISTERED.json');parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--fixtures',type=Path);parser.add_argument('--core-root',type=Path,default=ROOT);parser.add_argument('--entry',type=Path)
 args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None)
 if args.preregister:save(args.output,catalog());print(args.output)
 elif args.builder:builder(args)
 else:controller(args)
