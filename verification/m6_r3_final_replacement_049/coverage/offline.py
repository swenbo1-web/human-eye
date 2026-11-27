"""049 fixed coverage replay; all timings are QA cost, never scientific performance.

Uses the original048 observation helper and exactly its79 frozen cases, plus
the separately declared 125/129, different031 refusal and shared zero contact.
"""
from __future__ import annotations
import argparse
from collections import Counter
from fractions import Fraction as Q
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
ROOT=Path('D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT')
RAW=ROOT/'coverage/offline'
PLAN=RAW/'PLAN_02.json'
OLD=VER/'m6_r3_witness_parity_048'
OLDRAW=Path('D:/HumanEye/runs/M6-048-R3-WITNESS-PARITY')
FPINS=ROOT/'candidate/PINS.json'
FSHA='d30196668038e72c1315c5f9a36825c2197b06a283006244e701594217622567'
PYTHON=Path('D:/he_m3_bvh032_private_654c1f69/venv/Scripts/python.exe')

def pin(path):
 p=Path(path).resolve(strict=True);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(path):return json.loads(Path(path).read_bytes())
def check(ref):assert pin(ref['path'])==ref;return Path(ref['path'])
def save(path,data):
 p=Path(path).resolve();assert p.is_relative_to(RAW);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf8',newline='\n') as out:json.dump(data,out,indent=2,allow_nan=False);out.write('\n')
 return pin(p)
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def helper():
 sys.path.insert(0,str(OLD))
 try:return load('_049_original048_replay',OLD/'replay.py')
 finally:sys.path.pop(0)
def exact(v):
 if isinstance(v,Q):return str(v)
 if isinstance(v,dict):return {k:exact(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)):return [exact(x) for x in v]
 return v
def cube(name,shift):
 vs=[[-1.,-1.,-1.],[1.,-1.,-1.],[1.,1.,-1.],[-1.,1.,-1.],[-1.,-1.,1.],[1.,-1.,1.],[1.,1.,1.],[-1.,1.,1.]]
 fs=[[0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]]
 return {'name':name,'vertices_world':[[x+shift for x in p] for p in vs],'faces':fs}

def prepare():
 RAW.mkdir(parents=True,exist_ok=True);assert pin(FPINS)['sha256']==FSHA
 old=read(OLDRAW/'FREEZE.json');replay=helper();loaded=replay.load_inputs(old)
 cases=[]
 for label,base in [('pressure129',Path('D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY/oracle')),
                    ('pressure125',Path('D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/pressure'))]:
  g=read(base/'FINAL_GEOMETRY.json');truth=read(base/'FINAL_INDEPENDENT_TRUTH.json')
  cases.append({'id':label,'kind':'plain','family':'pressure','endpoints':[g['left'],g['right']],
    'ids':[g[x]['name'] for x in ('left','right')],'args':{'retain_exact_rank':True},
    'geometry':pin(base/'FINAL_GEOMETRY.json'),'truth':pin(base/'FINAL_INDEPENDENT_TRUTH.json'),
    'expected_q':truth['distance_squared_exact'],'canonical':truth['canonical_native_face_pair'],
    'unique_exact_points':truth['unique_witness_world_exact']})
 old031=load('_049_original031_fixture',VER/'m6_bvh_work_credit_031/test_controls.py')
 a,b=old031.problem('pair129')
 cases.append({'id':'original031_different_pair129','kind':'plain','family':'historical031',
    'endpoints':[{'name':m.name,'vertices_world':list(map(list,m.vertices)),'faces':list(map(list,m.faces))} for m in (a,b)],
    'ids':[a.name,b.name],'args':{'retain_exact_rank':True},'expected_q':'3','canonical':[0,0],
    'proof':'Parallel planes x+y+z=0 and3 give squared separation3, attained at source row0 centroids (0,0,0)/(1,1,1).',
    'historical_unknowns':[pin(VER/'m6_bvh_work_credit_031/private/controls/attempt_003_Gmain'/name) for name in ('pair129_A.json','pair129_G.json')],
    'generator':pin(VER/'m6_bvh_work_credit_031/test_controls.py'),'generator_dependency':pin(VER/'m6_bvh_projection_yield_030/test_controls.py')})
 for name,(family,endpoints,ids,args) in loaded.items():
  case={'id':'old048_'+name,'kind':'plain','family':family,'endpoints':endpoints,'ids':ids,'args':args,
    'old048_ordinary':pin(OLDRAW/'primary_001'/name/'ORDINARY.json')}
  if name=='closed-044':
   t=read(old['family']['truth']['path']);case.update(expected_q=t.get('exact_distance_squared_world_m2',t.get('distance_squared')),canonical=t.get('canonical_source_triangle_pair',t.get('input_pair')))
  cases.append(case)
 assert len(loaded)==79
 endpoints=[cube('Zero_A',0),cube('Zero_B',2)]
 for kind in ('plain','shared'):
  cases.append({'id':'analytic_unique_zero_'+kind,'kind':kind,'family':'shared_zero','endpoints':endpoints,
    'ids':['Zero_A','Zero_B'],'args':{'retain_exact_rank':True},'expected_q':'0','canonical':[2,0] if kind=='plain' else None,
    'unique_exact_points':[['1','1','1'],['1','1','1']],
    'proof':'Closed cubes [-1,1]^3 and[1,3]^3 intersect only at(1,1,1), on support plane x+y+z=3. Their interiors are disjoint, so closed relation touching. For ordinary distance native row2/0 is earliest of 25 corner-member pairs; shared contact permits the original first valid native pair.'})
 runtime={k:old['runtime'][k] for k in ('A','C')};f=read(FPINS)
 runtime['F']={'site':f['site'],'identity':f['identity'],'binding':f['binding'],'source':{
    name:pin(Path(f['site'])/'human_eye_plugin'/name) for name in ('surface_proximity.py','task_query.py')}}
 for arm,item in runtime.items():
  binding=read(check(item['binding']));assert len(binding['source_files'])==(145 if arm=='F' else 143)
  for src in binding['source_files']:assert pin(Path(item['site'])/src['path'])['sha256']==src['sha256']
 frozen=save(RAW/'CASES_02.json',cases)
 plan={'schema':'m6-049-fixed-offline-coverage-v1','contract':'4929a0c147e78c71f965b8d688174352266cf89f',
   'candidate':pin(FPINS),'source':pin(__file__),'old048_freeze':pin(OLDRAW/'FREEZE.json'),
   'old048_helper':pin(OLD/'replay.py'),'old048_helper_dependency':pin(OLD/'freeze.py'),'cases':frozen,
   'runtime':runtime,'order':['A','C','F'],'case_count':len(cases),'ordinary_and_diagnostic':'unprofiled first original return then separate same-input source/witness observation',
   'additional_controls':['face/index refusal','fixed short original service deadline context (separate QA only)','cooperative cancellation identity',
       'immutable per-mesh source reference replacement invalidates cache','mutable numpy source is never treated as immutable cache'],
   'Yanyite':'owned by separate agent; not repeated here','limits':{'faces':4096,'narrow':16384,'work':1179648,'deadline_s':30},
   'comparison_policy':'A known to F unknown is failure; A unknown to F known needs independent exact truth; C incremental capability loss is explicitly reported; preserved common witness limitation is not a scalar loss',
   'Blender':0,'scientific_timing':False}
 print(save(PLAN,plan),flush=True)

def runtime(plan,arm):
 item=plan['runtime'][arm];binding=read(check(item['binding']))
 for src in binding['source_files']:assert pin(Path(item['site'])/src['path'])['sha256']==src['sha256']
 sys.path.insert(0,item['site'])
 from human_eye_plugin import surface_proximity,task_query
 from human_eye_plugin.runtime_identity import runtime_identity
 import numpy as np
 identity=runtime_identity(mode='live');assert identity['source_sha256']==item['identity']['source_sha256']
 assert len(identity['source_files'])==(145 if arm=='F' else 143)
 assert (surface_proximity.MAX_FACES,surface_proximity.MAX_NARROW_PHASE_PAIRS,surface_proximity.MAX_WORK_UNITS)==(4096,16384,1179648)
 return surface_proximity,task_query,np,identity

def shared(runtime,case,diagnostic):
 kernel,query,np,identity=runtime
 from human_eye_plugin.active_observation_images import _meshes_from_objects
 from human_eye_plugin.scene_cache import SpatialSceneCache
 meshes=_meshes_from_objects([(x['vertices_world'],x['faces'],('049zero',i),x['name']) for i,x in enumerate(case['endpoints'])])
 graph={};metrics={};deadline=time.monotonic()+30;original_closed=query._closed_solid_pair_measurement;original_surface=query._surface_pair_measurement
 def checktime(stage):
  if time.monotonic()>=deadline:raise TimeoutError(stage)
 def closed(*args,**kw):
  value=original_closed(*args,**kw);h=kw.get('prepared_holder') or {};contact=h.get('boundary_contact')
  graph.update(pair=h.get('pair'),trees=h.get('trees'))
  graph['closed_post']={'pair_present':h.get('pair') is not None,'trees_present':h.get('trees') is not None,
    'boundary_contact_present':contact is not None,'contact_pair_identity':bool(contact and contact.get('pair') is h.get('pair')),
    'contact_point':exact(contact.get('point')) if contact else None,'contact_native_rows':contact.get('triangles') if contact else None}
  return value
 def surface(*args,**kw):
  graph['surface_pre']={'same_pair':kw.get('prepared_pair') is graph.get('pair'),'same_trees':kw.get('prepared_trees') is graph.get('trees'),
    'boundary_contact_supplied':kw.get('boundary_contact') is not None}
  return original_surface(*args,**kw)
 if diagnostic:query._closed_solid_pair_measurement=closed;query._surface_pair_measurement=surface
 start=time.perf_counter_ns();cpu=time.process_time_ns()
 try:
  facts,result=query._closed_surface_facts(*meshes,{'closed_solid_relation','surface_proximity'},SpatialSceneCache(),checktime,
    {'source':'049_unique_zero_control'},metrics,rank=True,witness_capture='049_native_diagnostic' if diagnostic else None)
 finally:query._closed_solid_pair_measurement=original_closed;query._surface_pair_measurement=original_surface
 graph.pop('pair',None);graph.pop('trees',None)
 return {'status':'returned','result':result,'public_fact':facts['surface_proximity'],'closed_fact':facts['closed_solid_relation'],
    'graph':graph,'metrics':metrics,'wall_ns':time.perf_counter_ns()-start,'cpu_ns':time.process_time_ns()-cpu}

def controls(rt):
 k,q,np,identity=rt;records={}
 supports_mesh_cache='_mesh_cache' in inspect.signature(k.measure_surface_proximity).parameters
 def measure(a,b,cache):
  return k.measure_surface_proximity(a,b,lambda _:None,**({'_mesh_cache':cache} if supports_mesh_cache else {}))
 def mesh(name,point):return SimpleNamespace(name=name,object_id=name,vertices=(tuple(point),),faces=((0,0,0),))
 left,right=mesh('a',(0.,0.,0.)),mesh('b',(1.,0.,0.));cache={}
 first=measure(left,right,cache)
 right.vertices=((2.,0.,0.),);changed=measure(left,right,cache)
 assert first['measurement_valid'] and changed['measurement_valid'] and first['distance_m']==1 and changed['distance_m']==2
 records['immutable_source_replaced']={'before':first,'after':changed,'per_mesh_cache_argument_supported':supports_mesh_cache}
 la=SimpleNamespace(name='na',object_id='na',vertices=np.array([[0.,0.,0.]]),faces=np.array([[0,0,0]],dtype=np.int32))
 rb=SimpleNamespace(name='nb',object_id='nb',vertices=np.array([[1.,0.,0.]]),faces=np.array([[0,0,0]],dtype=np.int32));cache={}
 first=measure(la,rb,cache);rb.vertices[0,0]=3.
 changed=measure(la,rb,cache)
 assert first['distance_m']==1 and changed['distance_m']==3
 records['mutable_source_changed']={'before':first,'after':changed,'cached_mesh_entries':len(cache),'per_mesh_cache_argument_supported':supports_mesh_cache}
 bad=SimpleNamespace(name='bad',object_id='bad',vertices=((0.,0.,0.),),faces=((0,0,7),))
 invalid=k.measure_surface_proximity(left,bad,lambda _:None);assert not invalid['measurement_valid'] and invalid['reason']=='surface_invalid_triangle_indices'
 records['invalid_indices']=invalid
 empty=SimpleNamespace(name='empty',object_id='empty',vertices=(),faces=())
 refused=k.measure_surface_proximity(left,empty,lambda _:None);assert not refused['measurement_valid'] and refused['reason']=='surface_geometry_work_limit'
 records['empty_source']=refused
 marker=RuntimeError('049 cooperative cancellation marker')
 def cancel(stage):raise marker
 try:k.measure_surface_proximity(left,right,cancel)
 except BaseException as exc:assert exc is marker
 else:raise AssertionError('cancellation swallowed')
 records['cancel']={'same_exception_propagated':True,'returned_result':False}
 from human_eye_plugin import live_service
 service=object.__new__(live_service.LiveSpatialService);service.request_budget_s=.01
 with service._request_budget() as budget:
  deadline=budget['deadline'];time.sleep(.012)
  try:k.measure_surface_proximity(left,right,service._check_request_budget)
  except live_service.RequestBudgetError as exc:
   assert exc.code=='live_request_expired' and budget['deadline']==deadline
   records['expiry']={'original_checker':True,'same_fixed_deadline':True,'code':exc.code,'control_context_seconds':.01,
      'scope':'short configured QA context only; all frozen ordinary and scientific distance calls retain30seconds'}
  else:raise AssertionError('expired original context returned a result')
 return records

def worker(plan_path,arm,output):
 plan=read(plan_path);assert check(plan['source'])==Path(__file__).resolve();check(plan['candidate']);replay=helper();rt=runtime(plan,arm)
 out=Path(output);out.mkdir();rows=[];began=time.perf_counter_ns();cpu=time.process_time_ns()
 report={'arm':arm,'status':'incomplete','identity':{key:rt[3][key] for key in ('source_sha256','distribution_version')},'rows':rows,'errors':[]}
 try:
  for case in read(check(plan['cases'])):
   if case['kind']=='plain':
    normal=replay.observe(rt,case['family'],case['endpoints'],case['ids'],case['args'],False,30,False)
    normalref=save(out/case['id']/'ORDINARY.json',normal)
    diagnostic=replay.observe(rt,case['family'],case['endpoints'],case['ids'],case['args'],True,30,False)
   else:
    normal=shared(rt,case,False);normalref=save(out/case['id']/'ORDINARY.json',exact(normal));diagnostic=shared(rt,case,True)
   diagref=save(out/case['id']/'DIAGNOSTIC.json',exact(diagnostic))
   assert normal['status']==diagnostic['status']=='returned',(case['id'],normal.get('traceback'),diagnostic.get('traceback'))
   value=normal['result'];checkrow={'case':case['id'],'normal':normalref,'diagnostic':diagref,'known':value['measurement_valid'],
    'reason':value.get('reason'),'work':value['work'],'distance_m':value.get('distance_m'),'status':'pass'}
   if value['measurement_valid'] and case.get('expected_q') is not None:
    key=value.get('_exact_distance_sq');assert key is not None
    n,d,e=key;assert Q(n,d)*Q(2)**e==Q(case['expected_q']),case['id']
    if case.get('unique_exact_points'):
     got=[value['point_a_world'],value['point_b_world']];want=[[float(Q(c)) for c in p] for p in case['unique_exact_points']]
     assert got==want,case['id']
   if case['kind']=='shared':
    assert normal['closed_fact']['status']=='measured' and normal['closed_fact']['value']=='touching'
    assert value['work'].get('zero_witness_reused') is True
    assert diagnostic['graph']['closed_post']['contact_pair_identity'] and diagnostic['graph']['surface_pre']['same_pair']
   rows.append(checkrow);print(arm,case['id'],checkrow['known'],flush=True)
  report['controls']=save(out/'REJECTION_LIFECYCLE_CONTROLS.json',exact(controls(rt)));report['status']='pass'
 except BaseException:report['errors'].append(traceback.format_exc())
 report.update(wall_ns=time.perf_counter_ns()-began,cpu_ns=time.process_time_ns()-cpu)
 save(out/'RESULTS.json',exact(report));return report['status']=='pass'

def run():
 plan=read(PLAN);assert check(plan['source'])==Path(__file__).resolve();out=RAW/'attempt_001';out.mkdir();records=[]
 start=time.perf_counter_ns()
 for arm in plan['order']:
  target=out/arm;command=[str(PYTHON),'-I','-B','-X','utf8',str(Path(__file__).resolve()),'worker','--plan',str(PLAN),'--arm',arm,'--output',str(target)]
  with (out/(arm+'.stdout')).open('xb') as stdout,(out/(arm+'.stderr')).open('xb') as stderr:
   process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   code=process.wait()
  result=read(target/'RESULTS.json') if (target/'RESULTS.json').exists() else None
  records.append({'arm':arm,'command':command,'pid':process.pid,'exit':code,'reaped':process.poll() is not None,
    'result':pin(target/'RESULTS.json') if result else None,'status':result.get('status') if result else 'missing'})
  print(arm,code,records[-1]['status'],flush=True)
 result={'status':'pass' if all(x['exit']==0 and x['status']=='pass' for x in records) else 'failed_or_incomplete',
    'plan':pin(PLAN),'arms':records,'wall_ns':time.perf_counter_ns()-start,'Blender':0,'scientific_timing':False,
    'cross_version_audit_pending':True}
 print(save(out/'RESULTS.json',result),flush=True);return result['status']=='pass'

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','run','worker'));p.add_argument('--plan',type=Path);p.add_argument('--arm');p.add_argument('--output',type=Path);a=p.parse_args()
 if a.mode=='prepare':prepare()
 elif a.mode=='run':sys.exit(0 if run() else 1)
 else:sys.exit(0 if worker(a.plan,a.arm,a.output) else 1)
