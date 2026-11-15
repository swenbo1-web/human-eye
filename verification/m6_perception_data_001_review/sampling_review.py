import json,time
from collections import Counter,defaultdict
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;P=HERE/'snapshot/verification/m6_perception_data_001'
def j(n):return json.loads((P/n).read_bytes())
def main():
 start=time.perf_counter();cpu=time.process_time();d=j('DATASET_INDEX.json');a=j('SAMPLER_AUDIT.json');split={x['id']:x for x in j('SPLIT.json')['mesh_membership']}
 with np.load(P/a['index']['path'],allow_pickle=False) as z:rows=z['rows']
 assert rows.shape==(1200,1024);flat=rows.reshape(-1);events=flat[::2];other=flat[1::2]
 assert np.all(events['state']+other['state']==1)
 for key in ('pair_index','F_row','source_vertex_id','pair_event_id'):assert np.array_equal(events[key],other[key])
 assert np.array_equal(events['pair_event_id'],np.arange(614400))
 assert np.all(np.sum(rows['state']==0,axis=1)==512)
 obs={o['id']:i for i,o in enumerate(d['observations'])};mapping={r['id']:np.load(P/r['region_mapping'],allow_pickle=False) for r in d['rois']}
 paths=[];labels=np.zeros((len(d['pairs']),384),bool);valid=[]
 for i,pair in enumerate(d['pairs']):
  source=split[pair['source_id']]
  assert source['group']==pair['group'] and source['split']==pair['split'] and source['mesh_id']==pair['mesh_id']
  if pair['split']=='development' and pair['usable_for_training']:
   paths.append((pair['group'],pair['mesh_id'],pair['pose_id'],pair['roi_id'],pair['combo_id'],i));valid.append(i)
  for state in (0,1):
   oid=pair['damaged_observation_id'] if state else pair['normal_observation_id'];o=d['observations'][obs[oid]]
   assert o['state']==('damaged' if state else 'normal')
   for key in ('source_id','mesh_id','pose_id','roi_id','group','split'):assert o[key]==pair[key]
  with np.load(P/d['observations'][obs[pair['damaged_observation_id']]]['supervision'],allow_pickle=False) as z:labels[i]=z['changed_mask']
 assert np.isin(flat['pair_index'],valid).all()
 endpoints=np.array([[obs[x['normal_observation_id']],obs[x['damaged_observation_id']]] for x in d['pairs']])
 assert np.array_equal(flat['observation_index'],endpoints[flat['pair_index'],flat['state']])
 fm=np.stack([mapping[x['roi_id']] for x in d['pairs']]);assert np.array_equal(flat['source_vertex_id'],fm[flat['pair_index'],flat['F_row']])
 # Build an independent ordered hierarchy from flat admissible paths, preserving published draws.
 def hierarchy(items,depth=0):
  groups=defaultdict(list)
  for p in items:groups[p[depth]].append(p)
  return [hierarchy(groups[key],depth+1) if depth<4 else groups[key][0][-1] for key in sorted(groups)]
 tree=hierarchy(paths);prob={}
 def visit(node,p=1.):
  for child in node:
   if isinstance(child,list):visit(child,p/len(node))
   else:prob[child]=p/len(node)
 visit(tree);saved={x['pair_id']:x for x in a['pair_weights']}
 for index,p in prob.items():assert abs(saved[d['pairs'][index]['id']]['probability_per_pair_event']-p)<1e-15
 rng=np.random.default_rng(1729)
 for k,e in enumerate(events):
  node=tree
  for _ in range(5):node=node[int(rng.integers(len(node)))]
  point=int(rng.integers(384));swap=int(rng.integers(2))
  assert node==e['pair_index'] and point==e['F_row'] and swap==e['state'],k
 weights=np.zeros(len(d['pairs']))
 for index,p in prob.items():weights[index]=p
 expected_positive=float(np.dot(weights,labels.mean(axis=1))*.5)
 actual_positive=int(np.sum(labels[flat['pair_index'],flat['F_row']]&(flat['state']==1)))
 assert abs(expected_positive-a['expected_positive_label_fraction'])<1e-15
 assert actual_positive==a['actual_positive_labels']
 pair_counts=np.bincount(events['pair_index'],minlength=len(d['pairs']))
 for index in valid:assert pair_counts[index]==saved[d['pairs'][index]['id']]['actual_pair_events']
 out={'status':'passed','saved_rows':len(flat),'paired_events':len(events),'deterministically_replayed_events':len(events),'normal_rows':int(np.sum(flat['state']==0)),
      'damaged_rows':int(np.sum(flat['state']==1)),'validation_rows':0,'usable_development_pairs':len(valid),'expected_positive_fraction':expected_positive,
      'actual_positive_rows':actual_positive,'actual_positive_fraction':actual_positive/len(flat),'normal_physical_observations':len({d['pairs'][i]['normal_observation_id'] for i in valid}),
      'numpy_version':np.__version__,'wall_s':time.perf_counter()-start,'CPU_s':time.process_time()-cpu,'training':0,'model_forwards':0,
      'limits':['Sampling state balance does not prove a model has stopped relying on position or learned abnormality.','Normal physical observations are reused; 614400 normal rows are not independent normal assets.']}
 (HERE/'SAMPLER_RESULTS.json').write_bytes((json.dumps(out,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(out))
if __name__=='__main__':main()
