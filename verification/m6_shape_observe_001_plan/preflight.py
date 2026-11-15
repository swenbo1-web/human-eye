"""Bound the next observation audit using fixed arrays; no model execution."""
import collections
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE=Path(__file__).resolve().parent
DATA=HERE.parent/'m6_shape_data_001_review/snapshot/verification/m6_shape_data_001'
PUBLIC=HERE.parent/'m6_shape_train_001_review/snapshot/verification/m6_shape_train_001'
INPUT_COMMIT='36694d0e3730a60b0611376b017f978f809a79c0'
BINS=[0.,.02,.10,float('inf')]

def read(p):return json.loads(p.read_bytes())
def stats(a):
    a=np.asarray(a,dtype=float)
    return {'count':len(a),'min':float(a.min()),'median':float(np.median(a)),'p95':float(np.quantile(a,.95)),'max':float(a.max())} if len(a) else {'count':0}
def distances(adj,seeds):
    d=np.full(len(adj),-1,dtype=np.int64);q=collections.deque(int(x) for x in seeds)
    for x in q:d[x]=0
    while q:
        i=q.popleft()
        for j in adj[i]:
            if d[j]<0:d[j]=d[i]+1;q.append(j)
    return d

start,cpu=time.perf_counter(),time.process_time()
data_index=DATA/'DATASET_INDEX.json';public_index=PUBLIC/'PUBLIC_DATASET_INDEX.json'
cases=[(c,DATA/'private/patches') for c in read(data_index)['cases']]
cases += [(c,PUBLIC/'private/public_data/patches') for c in read(public_index)['cases'] if c['purpose']=='validation']
records=[];evidence=[]
for c,root in cases:
    if c['normal_control']:continue
    folder=root/c['patch_id'];name=c['id'].split('/')[-1]
    paths=[folder/'graph.npz',folder/'labels'/(name+'.npz'),folder/'inputs'/(name+'.npz')]
    for p in paths:evidence.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    with np.load(paths[0],allow_pickle=False) as z:g={k:z[k] for k in z.files}
    with np.load(paths[1],allow_pickle=False) as z:S=z['damaged_mask'];target=z['target_world_m']
    with np.load(paths[2],allow_pickle=False) as z:scale=float(z['scale_m'])
    magnitude=np.linalg.norm(target[S],axis=1)/scale;energy=magnitude*magnitude
    adj=[[] for _ in S]
    for i,j in g['edge_index'].T:adj[int(i)].append(int(j))
    d_clean=distances(adj,np.flatnonzero(~S))[S]
    d_fixed=distances(adj,np.flatnonzero(~g['free_mask']))[S]
    assert np.all(d_clean>=0) and np.all(d_fixed>=0)
    group='development' if c['purpose']=='development_train_pool' else 'validation_'+c['position_group']
    bins=[]
    for lo,hi in zip(BINS[:-1],BINS[1:]):
        selected=(magnitude>lo)&(magnitude<=hi)
        bins.append({'low_exclusive':lo,'high_inclusive':hi if np.isfinite(hi) else None,'points':int(selected.sum()),'squared_target_energy':float(energy[selected].sum())})
    records.append({'id':c['id'],'source':c['source'],'group':group,'support_points':len(magnitude),'target_energy':float(energy.sum()),
                    'magnitude_over_observed_scale':stats(magnitude),'bins':bins,
                    'max_hops_to_label_clean':int(d_clean.max()),'max_hops_to_input_fixed':int(d_fixed.max()),
                    'support_points_over_K12_from_fixed':int((d_fixed>12).sum()),'support_energy_over_K12_from_fixed':float(energy[d_fixed>12].sum())})
summary={}
for group in ('development','validation_center','validation_offcenter'):
    rs=[r for r in records if r['group']==group];total=sum(r['support_points'] for r in rs);energy=sum(r['target_energy'] for r in rs)
    summary[group]={'dented_observations':len(rs),'support_points':total,'target_energy':energy,
      'bins':[{'low_exclusive':BINS[i],'high_inclusive':BINS[i+1] if i<2 else None,
               'points':sum(r['bins'][i]['points'] for r in rs),
               'point_fraction':sum(r['bins'][i]['points'] for r in rs)/total,
               'energy_fraction':sum(r['bins'][i]['squared_target_energy'] for r in rs)/energy} for i in range(3)],
      'case_max_hops_to_label_clean':stats([r['max_hops_to_label_clean'] for r in rs]),
      'case_max_hops_to_input_fixed':stats([r['max_hops_to_input_fixed'] for r in rs]),
      'points_over_K12_from_fixed':sum(r['support_points_over_K12_from_fixed'] for r in rs),
      'energy_fraction_over_K12_from_fixed':sum(r['support_energy_over_K12_from_fixed'] for r in rs)/energy}
out={'cycle':'M6-SHAPE-OBSERVE-001 planning preflight','input_commit':INPUT_COMMIT,
     'scope':'geometry/label denominators and topological reach only; no model inference, training, threshold selection or Bunny arrays/scoring; public index metadata includes reserved Bunny records',
     'diagnostic_bins':'(0,.02],(.02,.10],(.10,+inf) in observed median-edge units; linked to old normal-error scales, not relabeling',
     'index_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [data_index,public_index]},
     'summary':summary,'cases':records,'evidence':evidence,'wall_s':time.perf_counter()-start,'cpu_s':time.process_time()-cpu}
(HERE/'PREFLIGHT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'summary':summary,'wall_s':out['wall_s'],'cpu_s':out['cpu_s']},indent=2))
