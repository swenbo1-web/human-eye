"""Check witness selection and seven full-source feature reconstructions."""
import sys
from pathlib import Path
import time
import json
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import review as r
start,cpu=time.perf_counter(),time.process_time()
expected=r.read(r.B/'EVIDENCE_PLAN.json')['evidence'];selected=[]
for source in ('Yanyite','Richie','Chipow','Yunhex'):
    options=[]
    for c in r.CASES:
        if c['source']!=source or not c['normal_control']:continue
        s=r.load(c)
        options.extend((-float(s['p'][i]),c['id'],int(s['m']['context_source_ids'][i])) for i in np.flatnonzero(s['g']['free_mask']))
    selected.append(min(options)[1:])
for group in ('center','offcenter'):
    options=[]
    for c in r.CASES:
        if c['purpose']!='validation' or c['normal_control'] or c['position_group']!=group:continue
        s=r.load(c);t=(s['ref']-s['obs'])/s['scale'];energy=np.sum(t*t,axis=1)
        winner=min((-float(energy[i]),int(s['m']['context_source_ids'][i])) for i in np.flatnonzero(s['l']['damaged_mask']))
        options.append((-float(energy.sum()),c['id'],winner[1]))
    selected.append(min(options)[1:])
assert selected==[(w['case_id'],w['source_vertex_id']) for w in expected]
sources={};records=[]
for case_id in sorted({cid for w in expected for cid in (w['case_id'],w['paired_normal_case_id'])}):
    c=r.LOOKUP[case_id];s=r.load(c)
    if c['source'] not in sources:
        p=(r.T/'private/public_data/sources/Stanford_Armadillo/snapshot.npz' if c['purpose']=='validation' else r.D/'private'/c['source']/'snapshot.npz')
        sources[c['source']]=r.npz(p)
    source=sources[c['source']];v=source['vertices'].copy();tri=source['triangles'];context=s['m']['context_source_ids'];v[context]=s['obs']
    crosses=np.cross(v[tri[:,1]]-v[tri[:,0]],v[tri[:,2]]-v[tri[:,0]])
    total=np.column_stack([np.bincount(tri.ravel(),weights=np.repeat(crosses[:,axis],3),minlength=len(v)) for axis in range(3)])
    normals=total/np.maximum(np.linalg.norm(total,axis=1)[:,None],np.finfo(float).tiny)
    full_edges=np.unique(np.sort(np.vstack([tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]]]),axis=1),axis=0)
    adj=[[] for _ in v]
    for i,j in full_edges:adj[int(i)].append(int(j));adj[int(j)].append(int(i))
    q=s['obs'];origin=q[~s['g']['free_mask']].mean(0)
    ei,ej=s['g']['edge_index'];scale=float(np.median(np.linalg.norm(q[ei]-q[ej],axis=1)))
    pos=(q-origin)/scale;node=[]
    for k,i in enumerate(context):
        nei=adj[i];delta=(v[nei]-v[i])/scale
        node.append([np.linalg.norm(pos[k]),np.mean(delta,axis=0)@normals[i],np.mean(1-np.clip(normals[nei]@normals[i],-1,1)),np.mean(np.linalg.norm(delta,axis=1)),np.log1p(len(nei)),s['g']['allowed_mask'][k],not s['g']['free_mask'][k]])
    d=pos[ej]-pos[ei];n=normals[context]
    edge=np.column_stack([np.sum(d*d,axis=1),np.sum(n[ei]*n[ej],axis=1),np.sum(n[ei]*d,axis=1),np.sum(n[ej]*d,axis=1)])
    errors={}
    for name,actual in [('positions',pos),('normals',n),('node_features',np.asarray(node)),('edge_features',edge)]:
        saved=s['i'][name].astype(float)
        assert np.allclose(actual,saved,atol=2e-6,rtol=2e-6),(case_id,name)
        errors[name]=float(np.max(np.abs(actual-saved)))
    assert np.array_equal(origin,s['i']['origin_world_m']) and scale==s['scale']
    records.append({'case_id':case_id,'maximum_absolute_raw64_minus_saved32':errors,'origin_scale_exact':True})
out={'status':'passed','preselected_witnesses_rederived':6,'full_source_cases':records,
     'method':'Independent full triangle cross accumulation with bincount and per-vertex adjacency mean; no author geometry/feature imports',
     'render_review':'Original six-by-six actual geometry image visually inspected; unlike patches do not establish equivalent shape or artistic abnormality',
     'new_training':0,'Bunny_arrays':0,'wall_s_before_final_write':time.perf_counter()-start,'CPU_s_before_final_write':time.process_time()-cpu}
(HERE/'EVIDENCE_AUDIT.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps(out,indent=2))
