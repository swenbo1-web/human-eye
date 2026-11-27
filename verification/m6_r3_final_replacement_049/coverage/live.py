"""049 ordinary fresh pressure reads from the already saved 044/045 artifacts.

No geometry generation or upstream writes. Run requires a new exclusive049 window.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import traceback

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
ROOT=Path('D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT')
RAW=ROOT/'coverage/live'
CYCLE=ROOT.name
FPINS=ROOT/'candidate/PINS.json'
FSHA='d30196668038e72c1315c5f9a36825c2197b06a283006244e701594217622567'
LEGACY=VER/'m6_r3_replacement_entry_045/boundary/run.py'
PLAN=RAW/'PLAN.json'
NOW=time.perf_counter_ns

def pin(path):
 p=Path(path).resolve(strict=True);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(path):return json.loads(Path(path).read_bytes())
def check(ref):assert pin(ref['path'])==ref;return Path(ref['path'])
def save(path,data):
 p=Path(path).resolve();assert p.is_relative_to(RAW);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x',encoding='utf8',newline='\n') as out:json.dump(data,out,indent=2,allow_nan=False);out.write('\n')
 return pin(p)
def binary(value):
 if type(value) is float:return {'f64':value.hex()}
 if isinstance(value,(list,tuple)):return [binary(x) for x in value]
 if isinstance(value,dict):return {k:binary(v) for k,v in value.items()}
 return value
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

def api():
 old=load('_049_unchanged045_pressure',LEGACY);old.RAW=RAW;old.CYCLE=CYCLE
 original,s1,gui,svc=old.api();gui.PRIVATE=RAW;gui.CYCLE=CYCLE;svc.CYCLE=CYCLE
 base=svc.Client
 class Client(base):
  def __init__(self,folder,owner,name,install):
   self.expected_source_count=install['source_count'];super().__init__(folder,owner,name,install)
  def open(self,name):
   hello,timing=self.call('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':CYCLE,'version':'1'}})
   ident=hello['result']['_meta']['human_eye'];assert ident['source_sha256']==self.source
   assert ident['source_file_count']==self.expected_source_count and ident['distribution_version']==self.version and ident['production_mode']
   self.call('notifications/initialized',notify=True);catalog,tools_time=self.call('tools/list')
   tool,=[t for t in catalog['result']['tools'] if t['name']=='human_eye_scene_observe']
   assert 'source_region_measurement' not in json.dumps(tool)
   event,=[x for x in [json.loads(v) for v in self.audit.read_bytes().splitlines() if v] if x.get('measurement_scope')=='service_constructor_only']
   self.server_pid=event['pid'];assert event['runtime_identity']['build_id']=='sha256:'+self.source and event['identity_check']['compatible']
   svc.save(self.folder/'STARTUP.json',{'hello':hello,'timing':timing,'catalog':catalog,'tools_time':tools_time,
       'actual_pid':self.server_pid,'startup_trace':event,'scoped_mode_advertised':False})
 svc.Client=Client
 return old,original,s1,gui,svc

def installations(original,s1):
 assert pin(FPINS)['sha256']==FSHA
 f=read(FPINS);old=original.installed(s1)
 arms={k:dict(old[k],source_count=143) for k in ('A','C')};arms['F']=dict(f['arm'],source_count=145)
 for arm,data in arms.items():
  path=Path(data['site_packages']).parent/'admin/RUNTIME_BINDING.json';binding=read(path)
  assert binding['identity']['source_sha256']==data['source_sha256'] and len(binding['source_files'])==data['source_count']
  for row in binding['source_files']:assert pin(Path(data['site_packages'])/row['path'])['sha256']==row['sha256']
 return arms

def freeze():
 RAW.mkdir(parents=True,exist_ok=True);old,original,s1,gui,svc=api();arms=installations(original,s1)
 cases=[];sources={str(LEGACY):pin(LEGACY),str(HERE/'live.py'):pin(HERE/'live.py')}
 for n,priorpath in [(129,Path('D:/HumanEye/runs/M6-045-R3-REPLACEMENT-ENTRY/boundary/attempt_001/RESULTS.json')),
                     (125,Path('D:/HumanEye/runs/M6-044-R3-FRESH-BUDGET/live_pressure/attempt_001/RESULTS.json'))]:
  historical=read(priorpath);prior=read(check(historical['plan']));asset=historical['saved_artifact'];check(asset)
  for ref in prior['support'].values():check(ref)
  sources.update(prior['sources'])
  cases.append({'id':str(n),'n':n,'saved_asset':asset,'prior_result':pin(priorpath),'prior_plan':historical['plan'],
      'geometry':prior['fixed']['FINAL_GEOMETRY.json'],'truth':prior['fixed']['FINAL_INDEPENDENT_TRUTH.json'],
      'request':prior['request'],'support':prior['support']})
  for field in ('geometry','truth'):check(cases[-1][field])
  assert len(read(cases[-1]['geometry']['path'])['left']['faces'])==n
  assert old.request()==prior['request']
 source_capture=VER/'m6_r3_fresh_budget_044/live_family/capture.py';sources[str(source_capture)]=pin(source_capture)
 plan={'schema':'m6-049-pressure-ordinary-plan-v1','cycle_id':CYCLE,'contract':'4929a0c147e78c71f965b8d688174352266cf89f',
   'candidate':pin(FPINS),'arms':arms,'order':'ACF','cases':cases,'sources':sources,'capture_source':pin(source_capture),
   'method':'two independently fresh ordinaryGUI reopens of existing immutable saved artifacts; each arm a new installed stdio and one original first request',
   'no_genesis_or_geometry_edits':True,'original_limits':{'faces':4096,'narrow':16384,'work':1179648,'request_seconds':30},
   'expected':{'129':'A and F known unique exact; C historical unknown retained','125':'A/C/F known unique exact'},
   'scientific_timing':False,'Blender_launched_during_freeze':False}
 print(save(PLAN,plan),flush=True)

def capture(host,folder,label,case,plan):
 reply=host.run(check(plan['capture_source']).read_text(encoding='utf8'),timeout_s=30);save(folder/(label+'_RPC.json'),reply)
 assert reply['response']['status']=='success'
 text,=[line.split(':',1)[1] for line in reply['response']['result']['result'].splitlines() if line.startswith('M6_044_CAPTURE:')]
 doc=json.loads(text);save(folder/(label+'.json'),doc);s=doc['source']
 assert s['pid']==host.pid and s['main_thread'] and not s['background'] and s['scale_length']==1. and s['frame']==1 and s['subframe']==0.
 assert Path(s['asset']).resolve()==host.workspace/'input.blend'
 objects={x['name']:x for x in doc['objects'] if x['type']=='MESH'};geom=read(check(case['geometry']))
 assert set(objects)=={geom[x]['name'] for x in ('left','right')}
 identity=[[1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.],[0.,0.,0.,1.]]
 for side in ('left','right'):
  want=geom[side];got=objects[want['name']];assert binary(got['matrix_world'])==binary(identity) and got['modifier_types']==[] and got['parent'] is None
  for mode in ('native','evaluated'):
   a=got[mode];assert binary(a['vertices_local'])==binary(want['vertices_world'])==binary(a['vertices_world_m'])
   assert a['triangles']==want['faces']==a['native_polygon_vertices']
   assert a['source_triangle_rows']==a['triangle_polygons']==list(range(case['n']))
 return doc

def validate(folder,row,case,plan,original):
 answer=row['answer'];body=answer['result'];mid=answer['timing']['id'];source=plan['arms'][row['arm']]['source_sha256']
 cfg=read(folder/'client/CONFIG.json');assert cfg['request_budget_s']==cfg['blender']['timeout_s']==30.
 sent,received=(read(folder/'client'/(mid+s)) for s in ('.TX.bin','.RX.bin'))
 assert sent['params']==case['request'] and sent['id']==received['id']==mid
 assert not answer['tool_error'] and not answer['rpc_error']
 assert json.loads(received['result']['content'][0]['text'])==body and body['binding']['runtime_source_sha256']==source
 events=[json.loads(x) for x in (folder/'client/AUDIT.jsonl').read_bytes().splitlines() if x]
 event,=[e for e in events if e.get('event')=='request_trace' and str(e['trace']['annotations'].get('mcp_request_id'))==mid]
 assert event['pid']==event['trace']['pid']==row['product_pid'] and event['runtime_identity']['build_id']=='sha256:'+source
 assert event['identity_check']['compatible'] and event['identity_check']['actual']['source_sha256']==source
 observed,=[e for e in events if e.get('event')=='observe' and e.get('request_id')==event['trace']['request_id']]
 assert observed['scene_revision']==body['binding']['scene_revision']
 facts,_=original.facts(body);assert set(facts)=={'surface_proximity'};sf=facts['surface_proximity'];value=sf.get('value')
 distance=value.get('distance_m') if isinstance(value,dict) else None;known=sf['status']=='measured' and distance is not None
 truth=read(check(case['truth']));expected=math.sqrt(float(Q(truth['distance_squared_exact'])))
 if known:
  assert binary(distance)==binary(expected)
  p=value['nearest_witness'];want=[[float(Q(x)) for x in pp] for pp in truth['unique_witness_world_exact']]
  assert binary([p['a'],p['b']])==binary(want)
 else:assert distance is None
 work=observed.get('task_work');norm=deepcopy(body);norm['binding']['runtime_source_sha256']='validated_source';norm['trace_id']='validated_trace'
 row.update(distance_known=known,distance_m=distance,unknown_reason=sf.get('reason'),surface_fact=sf,work=work,
   native_source_pair=truth['canonical_native_face_pair'] if known else None,
   native_index_scope='independent unique point/source mapping; not a native-row field added to the public fact',
   trace=event['trace'],request=pin(folder/'client'/(mid+'.TX.bin')),response=pin(folder/'client'/(mid+'.RX.bin')),semantic=binary(norm))

def cell(folder,host,arm,case,plan,svc,original):
 folder.mkdir();client=None;row={'arm':arm,'errors':[],'started_ns':NOW(),'host_pid':host.pid}
 try:
  client=svc.Client(folder/'client',host,'Pressure',plan['arms'][arm]);client.open('Pressure')
  row.update(product_pid=client.server_pid,wrapper_pid=client.worker.pid,ready_ns=NOW())
  answer=client.observe(case['request']);row['reply_decoded_ns']=NOW();row['answer']=answer
  row['business_ns']=row['reply_decoded_ns']-answer['timing']['started_ns']
 except BaseException:row['errors'].append(traceback.format_exc())
 finally:
  if client:
   try:
    code=client.close();row['product_close']=read(folder/'client/CLOSE.json')
    assert code==0 and row['product_close']['method']=='eof' and not client.reader.is_alive()
   except BaseException:row['errors'].append(traceback.format_exc())
 if not row['errors']:
  try:validate(folder,row,case,plan,original)
  except BaseException:row['errors'].append(traceback.format_exc())
 row.update(ended_ns=NOW(),valid=not row['errors']);save(folder/'CELL.json',row)
 print(case['id'],arm,row['valid'],row.get('distance_known'),flush=True);return row

def run(window_path):
 plan=read(PLAN);check(plan['candidate']);window=read(window_path)
 assert window['cycle_id']==CYCLE and window['status']=='available' and window.get('token')
 for ref in plan['sources'].values():check(ref)
 old,original,s1,gui,svc=api();assert installations(original,s1)==plan['arms']
 output=RAW/'attempt_001';output.mkdir();allrows=[]
 report={'schema':'m6-049-pressure-ordinary-results-v1','plan':pin(PLAN),'window':pin(window_path),'started_ns':NOW(),'cases':[],'errors':[]}
 for case in plan['cases']:
  folder=output/case['id'];folder.mkdir();host=None;one={'id':case['id'],'cells':{},'errors':[]}
  try:
   gui.ASSET_SHAS={case['saved_asset']['sha256']:'049_frozen_pressure_'+case['id']}
   host=gui.Owned(folder/'native',case['saved_asset'],case['support'],window);one['host_pid']=host.pid
   before=capture(host,folder,'BEFORE',case,plan)
   for arm in plan['order']:one['cells'][arm]=cell(folder/arm,host,arm,case,plan,svc,original)
   after=capture(host,folder,'AFTER',case,plan);assert binary(before)==binary(after);one['scene_preserved']=True
  except BaseException:one['errors'].append(traceback.format_exc())
  finally:
   if host:
    try:one['close']=host.close();assert one['close']['status']=='pass' and one['close']['process_reaped'] and one['close']['forced'] is None
    except BaseException:one['errors'].append(traceback.format_exc())
  one['valid']=not one['errors'] and len(one['cells'])==3 and all(c['valid'] for c in one['cells'].values())
  one['F_restores_A_coverage']=one['valid'] and one['cells']['A']['distance_known'] and one['cells']['F']['distance_known']
  if one['valid'] and one['cells']['A']['distance_known'] and one['cells']['F']['distance_known']:
   assert one['cells']['A']['semantic']==one['cells']['F']['semantic']
  allrows.extend(one['cells'].values());report['cases'].append(one);save(folder/'RESULTS.json',one)
 report.update(ended_ns=NOW(),status='pass' if len(report['cases'])==2 and all(c['valid'] and c['F_restores_A_coverage'] for c in report['cases']) else 'failed_or_incomplete')
 report['full_lifecycle_wall_ns']=report['ended_ns']-report['started_ns'];print(save(output/'RESULTS.json',report),flush=True)
 return 0 if report['status']=='pass' else 1

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('mode',choices=('freeze','run'));p.add_argument('--window',type=Path);a=p.parse_args()
 if a.mode=='freeze':freeze()
 else:sys.exit(run(a.window))
