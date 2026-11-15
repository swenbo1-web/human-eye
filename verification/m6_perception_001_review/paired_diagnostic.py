"""Explanatory score-reuse diagnostic, not an inference candidate."""
import json,time,importlib.util
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;SNAP=HERE/'snapshot';P=SNAP/'verification/m6_perception_001';AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
spec=importlib.util.spec_from_file_location('independent_ring',HERE.parent/'m6_shape_ring_001_review/review.py');prev=importlib.util.module_from_spec(spec);spec.loader.exec_module(prev)
def local(s):return SNAP/Path(s).relative_to(AUTHOR)
def z(p):
 with np.load(p,allow_pickle=False) as a:return {k:a[k] for k in a.files}
def select(score,area,ids):
 chosen=np.zeros(len(score),bool);used=0.;budget=float(area.sum())*.25
 for i in np.lexsort((ids,-score)):
  if used+area[i]>budget:break
  chosen[i]=True;used+=area[i]
 return chosen
def main():
 start=time.perf_counter();cpu=time.process_time()
 rows=json.loads((P/'EVALUATION.json').read_bytes())['cases'];ix={r['id']:r for r in json.loads((P/'PREDICTIONS.json').read_bytes())['cases']}
 source={r['id']:r for r in json.loads((SNAP/'verification/m6_shape_ring_001/RESIDUALS.json').read_bytes())['cases']}
 old=json.loads((SNAP/'verification/m6_shape_ring_001/EVALUATION.json').read_bytes());old={r['id']:r for r in old['cases']}
 normals={r['patch_id']:z(local(ix[r['id']]['path'])) for r in rows if r['normal_control']}
 out=[]
 for r in rows:
  if r['normal_control']:continue
  p=z(local(ix[r['id']]['path']));normal=normals[r['patch_id']];assert np.array_equal(p['free_source_ids'],normal['free_source_ids'])
  labels=z(local(old[r['id']]['score_path']))['support'];geom=z(local(source[r['id']]['path']));area=geom['area']
  item={k:r[k] for k in ('id','patch_id','purpose','position_group')}
  for tag,scores in [('damaged_current',p['scores'].astype(float)),('normal_counterpart',normal['scores'].astype(float))]:
   chosen=select(scores,area,p['free_source_ids']);item[tag]={**prev.rank(labels,scores),'area_recall':float(area[labels&chosen].sum()/area[labels].sum()),'support_score_mean':float(scores[labels].mean()),'normal_score_mean':float(scores[~labels].mean())}
  delta=p['scores'].astype(float)-normal['scores'].astype(float)
  item['paired_change']={'support_score_increase_fraction':float((delta[labels]>0).mean()),'support_change_mean':float(delta[labels].mean()),'outside_change_abs_mean':float(np.abs(delta[~labels]).mean())}
  out.append(item)
 groups={}
 for name,subset in [('development',[r for r in out if r['purpose']=='development_train_pool']),('validation_center',[r for r in out if r['purpose']=='validation' and r['position_group']=='center']),('validation_offcenter',[r for r in out if r['purpose']=='validation' and r['position_group']=='offcenter'])]:
  summaries={}
  for tag in ('damaged_current','normal_counterpart'):
   summaries[tag]={}
   for key in ('ROC_AUC','AP','area_recall','support_score_mean','normal_score_mean'):
    patches={pid:[r[tag][key] for r in subset if r['patch_id']==pid] for pid in sorted({r['patch_id'] for r in subset})}
    summaries[tag][key]=float(np.mean([np.mean(v) for v in patches.values()]))
  summaries['cases']=len(subset);summaries['patches']=len({r['patch_id'] for r in subset});summaries['paired_change_mean']=float(np.mean([r['paired_change']['support_change_mean'] for r in subset]));groups[name]=summaries
 result={'status':'completed_explanatory_only','groups':groups,'cases':out,'scope':'Normal counterpart scores at same IDs evaluated against dent labels; privileged paired reference diagnostic only. Correlation does not prove one causal mechanism. No new model, fit or threshold.', 'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu}
 (HERE/'PAIRED_DIAGNOSTIC.json').write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(groups))
if __name__=='__main__':main()
