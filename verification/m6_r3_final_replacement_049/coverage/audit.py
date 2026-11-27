"""Raw-only049 coverage audit. No tested runtime or Blender import."""
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import time
from collections import Counter

HERE=Path(__file__).resolve().parent
VER=HERE.parents[1]
RAW=Path('D:/HumanEye/runs/M6-049-R3-FINAL-REPLACEMENT/coverage')

def pin(path):
 p=Path(path).resolve(strict=True);b=p.read_bytes();return dict(path=str(p),bytes=len(b),sha256=hashlib.sha256(b).hexdigest())
def read(path):return json.loads(Path(path).read_bytes())
def check(ref):assert pin(ref['path'])==ref;return Path(ref['path'])
def bits(v):
 if type(v) is float:return ('f64',struct.pack('<d',v).hex())
 if isinstance(v,dict):return {k:bits(x) for k,x in v.items()}
 if isinstance(v,(tuple,list)):return [bits(x) for x in v]
 return v
def native(row):
 v=row['result'];pair=v.get('exact_witness_triangles',{}).get('indices',v.get('witness_triangle_indices'))
 return pair if pair is not None else row.get('witness',{}).get('winner_native_rows')
def semantic(row):
 v=row['result'];keys=('measurement_valid','reason','distance_m','point_a_world','point_b_world','direction_a_to_b',
  'witness_status','witness_reason','direction_status','direction_reason','method','topology')
 return bits({k:v[k] for k in keys if k in v})

def main():
 started=time.perf_counter_ns();cpu=time.process_time_ns()
 plan=read(RAW/'offline/PLAN_02.json');cases=read(check(plan['cases']));run=read(RAW/'offline/attempt_001/RESULTS.json')
 assert run['status']=='pass';out=RAW/'AUDIT_FINAL.json';errors=[];rows=[];changes=[];native_checks=0
 spec=importlib.util.spec_from_file_location('_049_independent029_fraction',VER/'m6_bvh_witness_projection_029/oracle.py')
 oracle=importlib.util.module_from_spec(spec);sys.modules[spec.name]=oracle;spec.loader.exec_module(oracle)
 refs={arm['arm']:check(arm['result']) for arm in run['arms']}
 armresults={arm:read(path) for arm,path in refs.items()}
 assert all(x['status']=='pass' and len(x['rows'])==len(cases) for x in armresults.values())
 for case in cases:
  arms={arm:{kind:read(RAW/'offline/attempt_001'/arm/case['id']/(kind.upper()+'.json')) for kind in ('ordinary','diagnostic')} for arm in 'ACF'}
  if case.get('old048_ordinary'):
   original=read(check(case['old048_ordinary']))
   for arm in 'AC':
    assert semantic(arms[arm]['ordinary'])==semantic(original[arm]),(case['id'],arm,'changed frozen048 ordinary result')
  # Audit the untouched return and the separately instrumented observation.
  for arm,pair in arms.items():
   normal,diag=pair['ordinary'],pair['diagnostic']
   assert semantic(normal)==semantic(diag),(case['id'],arm,'diagnostic changed semantic return')
   known=normal['result']['measurement_valid']
   if known:
    sourcepair=native(diag);points=diag.get('witness',{}).get('exact_world_witness')
    if points is None:points=diag['result'].get('exact_witness_triangles',{}).get('points_m')
    if points is None and case.get('unique_exact_points'):points=case['unique_exact_points']
    if points is not None and sourcepair is not None:
     assert all(type(i) is int and 0<=i<len(mesh['faces']) for i,mesh in zip(sourcepair,case['endpoints']))
     exact_points=[tuple(map(Q,p)) for p in points]
     for point,index,mesh in zip(exact_points,sourcepair,case['endpoints']):
      triangle=[tuple(Q(x) for x in mesh['vertices_world'][v]) for v in mesh['faces'][index]]
      assert oracle.triangle_distance([point]*3,triangle)[0]==0,(case['id'],arm,'source membership')
      native_checks+=1
     sq=sum((a-b)**2 for a,b in zip(*exact_points))
     if case.get('expected_q') is not None:assert sq==Q(case['expected_q'])
     if case.get('canonical') is not None:assert sourcepair==case['canonical'],(case['id'],arm,sourcepair)
    if case['kind']=='shared':
     assert normal['closed_fact']['value']=='touching' and normal['result']['distance_m']==0.
     assert normal['result']['point_a_world']==normal['result']['point_b_world']==[1.,1.,1.]
   else:
    assert normal['result'].get('distance_m') is None and normal['result'].get('point_a_world') is None
  a,c,f=(arms[x]['ordinary']['result'] for x in 'ACF')
  label='same_status'
  if a['measurement_valid'] and not f['measurement_valid']:label='FAIL_A_known_F_unknown';errors.append({'case':case['id'],'classification':label})
  elif not a['measurement_valid'] and f['measurement_valid']:label='F_new_known'
  elif not a['measurement_valid'] and not f['measurement_valid']:label='preserved_A_unknown'
  if c['measurement_valid'] and not f['measurement_valid']:changes.append({'case':case['id'],'classification':'C_incremental_ability_not_retained','A_known':a['measurement_valid'],'F_reason':f.get('reason')})
  if a['measurement_valid'] and f['measurement_valid']:
   same=semantic(arms['A']['ordinary'])==semantic(arms['F']['ordinary'])
   if not same:
    if case['id']=='old048_coplanar_crossing_multifeature_tie':label='legal_multifeature_point_difference'
    else:errors.append({'case':case['id'],'classification':'A_F_public_semantic_difference'})
   if case['kind']!='shared':
    na,nf=(native(arms[x]['diagnostic']) for x in 'AF')
    if na is not None and nf is not None and na!=nf:errors.append({'case':case['id'],'classification':'native_pair_difference','A':na,'F':nf})
  rows.append({'case':case['id'],'classification':label,'status_by_arm':{arm:{'known':v['ordinary']['result']['measurement_valid'],
    'reason':v['ordinary']['result'].get('reason'),'witness_status':v['ordinary']['result'].get('witness_status'),
    'distance_m':v['ordinary']['result'].get('distance_m'),'native_pair_diagnostic':native(v['diagnostic']),
    'solver_path':v['ordinary']['result']['work'].get('solver_path'),
    'work_units':v['ordinary']['result']['work']['work_units'],'narrow_phase_pairs':v['ordinary']['result']['work']['narrow_phase_pairs']} for arm,v in arms.items()}})
 controls={arm:read(check(armresults[arm]['controls'])) for arm in 'ACF'}
 statuses={};shared_graph={}
 for arm in 'ACF':
  counter=Counter()
  for case in cases:
   record=read(RAW/'offline/attempt_001'/arm/case['id']/'ORDINARY.json')
   counter['scalar_known' if record['result']['measurement_valid'] else 'scalar_unknown']+=1
   counter['public_fact_'+record['public_fact']['status']]+=1
   counter['witness_'+record['result']['witness_status']]+=1
  statuses[arm]=dict(counter)
  path=RAW/'offline/attempt_001'/arm/'analytic_unique_zero_shared/DIAGNOSTIC.json'
  shared_graph[arm]={'raw':pin(path),'graph':read(path)['graph'],
    'contact_point_coordinate_frame':'prepared pair integer frame; not world metres',
    'original_public_world_points':[[1.,1.,1.],[1.,1.,1.]],
    'source_pair_contract':'first valid shared closed contact [9,4]; ordinary distance canonical [2,0] is a separate path'}
 livepath=RAW/'live/attempt_001/RESULTS.json';live=read(livepath);assert live['status']=='pass'
 for case in live['cases']:
  assert case['valid'] and case['F_restores_A_coverage'] and case['close']['status']=='pass'
  assert case['close']['process_reaped'] and not case['close']['released_port']['any_listener']
 report={'schema':'m6-049-independent-coverage-audit-v1','status':'pass' if not errors else 'fail',
  'source':pin(__file__),'plan':pin(RAW/'offline/PLAN_02.json'),'raw_execution':pin(RAW/'offline/attempt_001/RESULTS.json'),
  'ordinary_pressure':pin(livepath),'offline_case_count':len(rows),'ordinary_and_diagnostic_calls':len(rows)*3*2,
  'independent_native_point_membership_checks':native_checks,'errors':errors,'C_incremental_capability_changes':changes,'rows':rows,
  'source_and_rejection_controls':{a:armresults[a]['controls'] for a in 'ACF'},
  'status_counts_by_arm':statuses,'shared_contact_graph_scope':shared_graph,
  'preserved_initial_raw_audit':pin(RAW/'AUDIT.json'),
  'original_048_oracles_reused':True,'G60_truth_scope':'Original048 frozen A/C semantics and separately reconstructed source-member witnesses; no new exhaustive all-pair oracle runs.',
  'shared_zero_scope':'unique analytic closed contact and actual pre/post preparation/contact identities; shared native pair is any valid original first contact',
  'Yanyite':'separate agent; omitted here','no_new_Blend_or_solver_calls_by_audit':True,
  'wall_ns':time.perf_counter_ns()-started,'cpu_ns':time.process_time_ns()-cpu}
 with out.open('x',encoding='utf8',newline='\n') as stream:json.dump(report,stream,indent=2);stream.write('\n')
 print(json.dumps({'status':report['status'],'audit':pin(out),'errors':errors,'C_changes':changes}))

if __name__=='__main__':main()
