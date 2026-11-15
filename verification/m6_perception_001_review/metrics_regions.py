"""Independent complete ranking, region selection and source-ID geometry audit."""
import json,time,hashlib,importlib.util
from pathlib import Path
from collections import defaultdict
import numpy as np
HERE=Path(__file__).resolve().parent;SNAP=HERE/'snapshot';P=SNAP/'verification/m6_perception_001';R=SNAP/'verification/m6_shape_ring_001';AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
spec=importlib.util.spec_from_file_location('own_ring',HERE.parent/'m6_shape_ring_001_review/review.py');lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
def j(p):return json.loads(Path(p).read_bytes())
def local(s):return SNAP/Path(s).relative_to(AUTHOR)
def z(p):
 with np.load(p,allow_pickle=False) as a:return {k:a[k] for k in a.files}
def check(k,a,b):lib.ck(k,a,b)
def pick(s,area,ids):
 result=np.zeros(len(s),bool);order=np.lexsort((ids,-s));value=0.;budget=area.sum()/4
 for i in order:
  if value+float(area[i])>budget:break
  result[i]=True;value+=float(area[i])
 return result
def geometry(p,w):
 return p.min(0),p.max(0),np.sum(p*w[:,None],axis=0)/w.sum() if w.sum()>0 else p.mean(0)
def main():
 start=time.perf_counter();cpu=time.process_time();ev=j(P/'EVALUATION.json');white={r['id']:r for r in j(P/'INPUT_WHITELIST.json')['cases']};cal=j(P/'CALIBRATION.json')
 ring={r['id']:r for r in j(R/'EVALUATION.json')['cases']};res={r['id']:r for r in j(R/'RESIDUALS.json')['cases']};pred={r['id']:r for r in j(P/'PREDICTIONS.json')['cases']}
 data={};recomputed={}
 for row in ev['cases']:
  cid=row['id'];old=z(local(ring[cid]['score_path']));g=z(local(res[cid]['path']));p=z(local(pred[cid]['path']));sel=z(local(row['selection_path']))
  check('selection_source_IDs',sel['free_source_ids'],g['free_source_ids']);check('prediction_source_IDs',p['free_source_ids'],g['free_source_ids'])
  check('selection_area',sel['area'],g['area']);check('selection_score',sel['new_score'],p['scores']);check('selection_valid',sel['valid_mask'],p['valid_mask'])
  scores={'perception':p['scores'].astype(float),**{k:old[k] for k in ('old_p','solid_point','ring_point')}}
  y=old['support'];strong=old['strong'];area=g['area'];edge=g['free_edge_index'];ell=float(g['ell']);result={}
  for cfg,score in scores.items():
   chosen=pick(score,area,g['free_source_ids']);key='attention_mask' if cfg=='perception' else 'A_'+cfg+'_selected';check('attention_selection',chosen,sel[key])
   result[cfg]={}
   for task,labels in [('support',y),('strong',strong)]:
    rm=lib.rank(labels,score)
    for k,v in rm.items():check('case_rank_'+k,row['configurations'][cfg]['rank'][task][k],v)
    op=lib.operation(labels,chosen,area,ell,edge)
    for k,v in op.items():check('case_A_'+k,row['configurations'][cfg]['A'][task][k],v)
    missed=lib.parts(labels&~chosen,edge);maxarea=max((area[c].sum() for c in missed),default=0)
    check('largest_missed_area',row['configurations'][cfg]['A'][task]['largest_missed_component_area_native'],maxarea)
    result[cfg][task]={'rank':rm,'A':op}
  b=scores['perception']>cal['threshold'];check('B_selection',b,sel['abnormal_mask']);result['B']={}
  for task,labels in [('support',y),('strong',strong)]:
   op=lib.operation(labels,b,area,ell,edge);result['B'][task]=op
   for k,v in op.items():check('case_B_'+k,row['B'][task][k],v)
  data[cid]={'scores':scores,'support':y,'strong':strong,'selection':sel,'geometry':g};recomputed[cid]=result
 normaldev=[r for r in ev['cases'] if r['normal_control'] and r['purpose']=='development_train_pool'];maxima=[data[r['id']]['scores']['perception'].max() for r in normaldev]
 check('fixed_q95',cal['threshold'],np.quantile(maxima,.95))
 groups={
  'development_center':[r for r in ev['cases'] if r['purpose']=='development_train_pool'],
  'validation_center':[r for r in ev['cases'] if r['purpose']=='validation' and r['position_group']=='center'],
  'validation_offcenter':[r for r in ev['cases'] if r['purpose']=='validation' and r['position_group']=='offcenter'],
  'development_normal_controls':normaldev,
  'validation_normal_controls':[r for r in ev['cases'] if r['normal_control'] and r['purpose']=='validation']}
 group_results={}
 for name,rows in groups.items():
  summary={}
  for cfg in ('perception','old_p','solid_point','ring_point'):
   summary[cfg]={}
   for task in ('support','strong'):
    target=ev['groups'][name]['configurations'][cfg];pool=lib.rank(np.concatenate([data[r['id']][task] for r in rows]),np.concatenate([data[r['id']]['scores'][cfg] for r in rows]))
    for k,v in pool.items():check('pool_'+k,target['rank'][task]['point_pool'][k],v)
    for stat in ('ROC_AUC','AP','area_recall'):
     patch=defaultdict(list)
     for row in rows:
      rec=recomputed[row['id']][cfg][task];v=rec['A'][stat] if stat=='area_recall' else rec['rank'][stat]
      if v is not None:patch[row['patch_id']].append(v)
     avg=float(np.mean([np.mean(v) for v in patch.values()])) if patch else None
     saved=target['A'][task]['patch_macro_area_recall']['value'] if stat=='area_recall' else target['rank'][task]['patch_macro_'+stat]['value']
     check('group_macro_'+stat,saved,avg)
     if task=='support':summary[cfg][stat]=avg
  group_results[name]=summary
 references=j(P/'REGION_REFERENCES.json')['regions'];region_reports=j(P/'REGION_REPORTS.json');bycase=defaultdict(lambda:defaultdict(list));refcount=0
 for ref,record in references.items():
  identity=record['identity'];facts=record['facts'];cid=identity['observation_id'];mode=identity['selection_mode'];w=white[cid];sel=data[cid]['selection'];payload=z(local(record['detail']['path']))
  canonical=json.dumps(identity,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
  assert ref=='m6perception://v1/region/'+hashlib.sha256(canonical).hexdigest()
  ids=payload['source_ids'];rows=np.searchsorted(sel['free_source_ids'],ids);check('region_source_IDs',sel['free_source_ids'][rows],ids)
  mask=sel['attention_mask'] if mode=='attention' else sel['abnormal_mask'];check('region_in_selection',mask[rows],np.ones(len(rows),bool))
  observed=np.load(local(w['observed']['path']),allow_pickle=False);points=observed[sel['free_context_ids'][rows]];area=sel['area'][rows];score=sel['new_score'][rows]
  for k,v in [('current_positions_native',points),('area',area),('scores',score),('valid_mask',sel['valid_mask'][rows])]:check('region_payload_'+k,payload[k],v)
  lo,hi,center=geometry(points,area);check('region_bbox_min',facts['geometry']['bbox_native']['min'],lo);check('region_bbox_max',facts['geometry']['bbox_native']['max'],hi);check('region_centroid',facts['geometry']['centroid_native'],center)
  check('region_area',facts['area_native'],area.sum());check('region_priority',facts['priority_native_area_times_score'],np.dot(area,score));check('region_count',facts['points'],len(ids))
  for k,v in [('min',score.min()),('mean',score.mean()),('max',score.max()),('p95',np.quantile(score,.95))]:check('region_score_'+k,facts['scores'][k],v)
  assert identity['observation_sha256']==w['observed']['sha256'] and identity['snapshot_sha256']==w['snapshot']['sha256']
  assert identity['region_source_ids_sha256']==hashlib.sha256(np.asarray(ids,dtype='<i8').tobytes()).hexdigest()
  bycase[cid][mode].append((rows,facts));refcount+=1
 for r in region_reports['cases']:
  cid=r['id'];sel=data[cid]['selection'];facts=j(local(r['structured_report']['path']));text=local(r['text_report']['path']).read_text(encoding='utf8')
  for mode,key in [('attention','attention'),('threshold','threshold_anomaly_prediction')]:
   # Region mode is 'threshold' for B in the bound identity.
   actual=bycase[cid].get(mode,[]);mask=sel['attention_mask'] if mode=='attention' else sel['abnormal_mask'];comps=lib.parts(mask,sel['free_edge_index'])
   check('region_union_count',sum(len(x[0]) for x in actual),int(mask.sum()));check('region_components',len(actual),len(comps))
   actualsets=sorted([tuple(x[0]) for x in actual]);expected=sorted([tuple(c) for c in comps]);assert actualsets==expected
   actual=sorted(actual,key=lambda x:(-x[1]['priority_native_area_times_score'],int(sel['free_source_ids'][x[0]].min())))
   displayed=facts[key]['top_regions'];expectedtop=actual[:3] if mode=='attention' else []
   assert [v['reference'] for v in displayed]==[v[1]['reference'] for v in expectedtop]
   check('fact_region_count',facts[key]['region_count'],len(actual));check('fact_remaining_count',facts[key]['remaining_region_count'],len(actual)-len(displayed))
   check('fact_remaining_area',facts[key]['remaining_area_native'],sum(v[1]['area_native'] for v in actual[len(displayed):]))
   for x in displayed:assert x['reference'] in text
  assert facts['inspection_scope']['kind']=='specified_task_F'
  assert facts['LLM_consumer_evaluation']=='not_run'
 out={'status':'passed','assertions':sum(lib.counts.values()),'checks':dict(lib.counts),'max_differences':dict(lib.maxdiff),'coverage':{'cases':len(ev['cases']),'A_case_configurations':len(ev['cases'])*4,'B_cases':len(ev['cases']),'main_groups':len(groups),'region_references':refcount},'group_results':group_results,'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu,'limits':['All saved region geometries independently reconstructed; no live Blender or model consumer','B reports remain unconfirmed model predictions','Unseen-source generalization not established']}
 (HERE/'METRICS_REGIONS_RESULTS.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps({k:out[k] for k in ('status','assertions','coverage','wall_s','CPU_s')}))
if __name__=='__main__':main()
