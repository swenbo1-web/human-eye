"""Independent checks of saved pairs, observation formulas and graph reachability."""
import os
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'): os.environ[k]='1'
from collections import deque
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE=Path(__file__).resolve().parent
SNAP=HERE/'snapshot'
BASE=SNAP/'verification/m6_shape_data_001'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
checks=[]


def read(path): return json.loads(path.read_bytes())
def local(path): return SNAP/Path(path).relative_to(AUTHOR)
def arrays(path):
    with np.load(path,allow_pickle=False) as z: return {k:z[k] for k in z.files}
def check(name,condition):
    if not condition: raise AssertionError(name)
    checks.append(name)
def edges_of(t): return np.unique(np.sort(np.concatenate((t[:,[0,1]],t[:,[1,2]],t[:,[2,0]])),axis=1),axis=0)
def hops(edge_index, n, starts):
    a=[[] for _ in range(n)]
    for i,j in edge_index.T: a[i].append(j)
    d=np.full(n,-1,dtype=int); q=deque(map(int,starts))
    for v in q: d[v]=0
    while q:
        i=q.popleft()
        for j in a[i]:
            if d[j]<0: d[j]=d[i]+1; q.append(int(j))
    return d


def independent_features(p,t,ctx,g):
    """Neighbor coordinate sums and bincount normal assembly, no author helpers."""
    e=edges_of(t)
    cross=np.cross(p[t[:,1]]-p[t[:,0]],p[t[:,2]]-p[t[:,0]])
    n=np.column_stack([sum(np.bincount(t[:,corner],weights=cross[:,axis],minlength=len(p)) for corner in range(3)) for axis in range(3)])
    lengths=np.linalg.norm(n,axis=1); n/=np.maximum(lengths[:,None],np.finfo(float).tiny)
    origin=p[ctx[~g['free_mask']]].mean(axis=0)
    a,b=g['edge_index']
    scale=np.median(np.linalg.norm(p[ctx[b]]-p[ctx[a]],axis=1))
    q=(p[ctx]-origin)/scale
    u,v=e.T
    degree=np.bincount(e.ravel(),minlength=len(p)); den=np.maximum(degree,1)
    neighbor=np.column_stack([np.bincount(u,weights=p[v,axis],minlength=len(p))+np.bincount(v,weights=p[u,axis],minlength=len(p)) for axis in range(3)])
    lap=(neighbor/den[:,None]-p)/scale
    length=np.linalg.norm(p[u]-p[v],axis=1)/scale
    var=1-np.clip((n[u]*n[v]).sum(axis=1),-1,1)
    mean_length=(np.bincount(u,weights=length,minlength=len(p))+np.bincount(v,weights=length,minlength=len(p)))/den
    mean_var=(np.bincount(u,weights=var,minlength=len(p))+np.bincount(v,weights=var,minlength=len(p)))/den
    h=np.column_stack([np.linalg.norm(q,axis=1),(lap*n).sum(axis=1)[ctx],mean_var[ctx],mean_length[ctx],np.log1p(degree[ctx]),g['allowed_mask'],~g['free_mask']])
    r=q[b]-q[a]; nc=n[ctx]
    ef=np.column_stack([(r*r).sum(axis=1),(nc[a]*nc[b]).sum(axis=1),(nc[a]*r).sum(axis=1),(nc[b]*r).sum(axis=1)])
    return {'node_features':h.astype(np.float32),'edge_features':ef.astype(np.float32),'positions':q.astype(np.float32),'normals':nc.astype(np.float32),'origin_world_m':origin,'scale_m':scale}


started,cpu=time.perf_counter(),time.process_time()
snapshot=read(HERE/'SNAPSHOT.json')
for row in snapshot['sources']:
    b=(SNAP/row['relative']).read_bytes()
    check('source '+row['relative'],len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'])
for row in snapshot['checked_records']:
    if row['group']=='private_local_files':
        b=local(row['path']).read_bytes()
        check('private '+str(Path(row['path']).relative_to(AUTHOR)),len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256'])
index=read(BASE/'DATASET_INDEX.json'); selection=read(BASE/'PATCH_SELECTION.json'); verification=read(BASE/'VERIFICATION.json')
groups=read(BASE/'SOURCE_GROUPS.json'); audit=read(BASE/'SOURCE_AUDIT.json')
check('one unresolved upstream group, no validation/test',groups['conservative_groups']==1 and groups['verified_independent_groups']==0 and not groups['splits']['validation'] and not groups['splits']['reserved_test'])
check('fixed counts',len(index['cases'])==231 and len(selection['patches'])==33 and sum(c['normal_control'] for c in index['cases'])==33)
sources={}
for s in audit['sources']:
    z=arrays(local(s['snapshot']['path'])); export=read(local(s['selected_export']['path']))
    check(s['name']+' frozen export mapping',np.array_equal(z['vertices'],export['vertices_world']) and np.array_equal(z['triangles'],export['triangles']) and np.array_equal(z['source_polygon_ids'],export['polygon_ids_by_triangle']))
    sources[s['name']]=z
rows=[]; graph_rows=[]; feature_rows=[]; support_total=0; normal_total=0; nf_total=0; label_error=0.; span_errors=[]; feature_inputs=[]
for patch in selection['patches']:
    folder=local(patch['private_directory']); m=arrays(folder/'mapping.npz'); g=arrays(folder/'graph.npz')
    source=sources[patch['source']]; p,t=source['vertices'],source['triangles']
    ctx=m['context_source_ids']; allow=m['allowed_source_ids']; area=set(allow.tolist()); pos={v:i for i,v in enumerate(allow)}
    inside=t[np.all(np.isin(t,allow),axis=1)]
    er=np.sort(np.concatenate((inside[:,[0,1]],inside[:,[1,2]],inside[:,[2,0]])),axis=1)
    e,counts=np.unique(er,axis=0,return_counts=True); boundary=np.unique(e[counts==1]); free=~np.isin(ctx,boundary)&np.isin(ctx,allow)
    check(patch['id']+' domain and mapping',len(allow)==384 and np.array_equal(boundary,m['boundary_source_ids']) and np.array_equal(g['free_mask'],free) and np.array_equal(np.load(folder/'reference_local.npy'),p[ctx]))
    check(patch['id']+' complete incident faces',np.array_equal(m['incident_source_face_ids'],np.flatnonzero(np.any(np.isin(t,allow),axis=1))))
    original_edges=edges_of(t); selected_edges=original_edges[np.all(np.isin(original_edges,ctx),axis=1)]
    rmap={v:i for i,v in enumerate(ctx)}; el=np.array([[rmap[a],rmap[b]] for a,b in selected_edges])
    check(patch['id']+' induced directed graph',np.array_equal(g['edge_index'],np.concatenate([el,el[:,::-1]]).T))
    dist=np.full((len(allow),len(allow)),np.inf); np.fill_diagonal(dist,0)
    for a,b in e: dist[pos[a],pos[b]]=dist[pos[b],pos[a]]=np.linalg.norm(p[a]-p[b])
    for k in range(len(allow)): dist=np.minimum(dist,dist[:,k,None]+dist[None,k,:])
    seed=patch['center_vertex_id']; d=dist[pos[seed]]; D=float(d[[pos[v] for v in boundary]].min())
    incident=t[np.any(t==seed,axis=1)]; normal=np.cross(p[incident[:,1]]-p[incident[:,0]],p[incident[:,2]]-p[incident[:,0]]).sum(axis=0); normal/=np.linalg.norm(normal)
    check(patch['id']+' independent induced distances',abs(D-patch['distance_to_boundary_m'])<1e-13)
    cases=[c for c in index['cases'] if c['patch_id']==patch['id']]
    for c in cases:
        obs=np.load(local(c['observed']['path']),allow_pickle=False); inp=arrays(local(c['input']['path'])); lab=arrays(local(c['labels']['path']))
        expected=p[ctx].copy(); support=[]
        if c['radius_ratio'] is not None:
            radius=c['radius_ratio']*D; amplitude=c['amplitude_ratio']*radius
            support=[int(v) for v in allow if v not in boundary and d[pos[v]]<radius]
            for v in support: expected[rmap[v]]-=amplitude*(1-(d[pos[v]]/radius)**2)**2*normal
        mask=np.isin(ctx,support); delta=p[ctx]-obs
        check(c['id']+' generated observation',np.max(np.abs(obs-expected))<1e-13 and int(mask.sum())==c['damaged_vertices'] and np.array_equal(obs[~mask],p[ctx][~mask]))
        check(c['id']+' labels and masks',np.array_equal(lab['target_world_m'],delta) and np.array_equal(lab['target_normalized'],(delta/float(inp['scale_m'])).astype(np.float32)) and np.array_equal(lab['damaged_mask'],mask) and np.array_equal(lab['normal_allowed_mask'],g['allowed_mask']&~mask) and np.array_equal(lab['normal_free_mask'],free&~mask))
        check(c['id']+' input dimensions and finite',set(inp)=={'node_features','edge_features','positions','normals','origin_world_m','scale_m','feature_names'} and inp['node_features'].shape==(len(ctx),7) and inp['edge_features'].shape==(g['edge_index'].shape[1],4) and all(np.isfinite(inp[k]).all() for k in inp if k!='feature_names'))
        check(c['id']+' observer transform',np.max(np.abs((obs-inp['origin_world_m'])/float(inp['scale_m'])-inp['positions']))<2e-6)
        error=float(np.linalg.norm(obs+lab['target_normalized']*float(inp['scale_m'])-p[ctx],axis=1).max()); label_error=max(label_error,error)
        support_total+=len(support); normal_total+=int(lab['normal_allowed_mask'].sum()); nf_total+=int(lab['normal_free_mask'].sum())
        if c['id'].endswith('sample_06'):
            to_fixed=hops(g['edge_index'],len(ctx),np.flatnonzero(~free)); to_clean=hops(g['edge_index'],len(ctx),np.flatnonzero(~mask))
            diam=max(hops(g['edge_index'],len(ctx),[int(v)])[mask].max() for v in np.flatnonzero(mask))
            graph_rows.append({'patch_id':patch['id'],'to_fixed_max':int(to_fixed[mask].max()),'to_clean_max':int(to_clean[mask].max()),'support_diameter':int(diam)})
        # This is a necessary geometric output-span check, not learned recovery.
        a,b=g['edge_index']; vector=inp['positions'][b].astype(float)-inp['positions'][a].astype(float)
        for v in np.flatnonzero(mask):
            basis=np.vstack([inp['normals'][v],vector[a==v]]).T.astype(float)
            target=lab['target_normalized'][v].astype(float)
            coeff,_,_,_=np.linalg.lstsq(basis,target,rcond=None)
            span_errors.append(float(np.linalg.norm(basis@coeff-target)))
        if patch['id'].endswith('patch_00') and (c['normal_control'] or c['id'].endswith('sample_06')):
            full=p.copy(); full[ctx]=obs; independent=independent_features(full,t,ctx,g)
            diffs={k:float(np.max(np.abs(independent[k]-inp[k]))) for k in independent}
            check(c['id']+' independent observation features',all(v<2e-5 for v in diffs.values()))
            feature_rows.append({'id':c['id'],'max_absolute_difference':diffs})
            if not c['normal_control']: feature_inputs.append((c['id'],full,t,ctx,g,independent))
    rows.append({'id':patch['id'],'source':patch['source'],'allowed':allow.tolist(),'center':int(seed)})
check('all label denominators',support_total==6042 and normal_total==82662 and nf_total==66793)
expected={x['patch_id']:x for x in verification['graph_statistics']}
check('independent graph reachability matches',all(r['to_fixed_max']==expected[r['patch_id']]['damaged_to_fixed_halo_max_hops'] and r['to_clean_max']==expected[r['patch_id']]['damaged_to_clean_max_hops'] and r['support_diameter']==expected[r['patch_id']]['support_diameter_hops'] for r in graph_rows))
overlaps=[]
for i,a in enumerate(rows):
    for b in rows[i+1:]:
        if a['source']==b['source']:
            x,y=set(a['allowed']),set(b['allowed']); inter=len(x&y)
            if inter: overlaps.append({'first':a['id'],'second':b['id'],'jaccard':inter/len(x|y)})
check('overlap denominator',len(overlaps)==19 and abs(max(x['jaccard'] for x in overlaps)-.9844961240310077)<1e-12)
check('output normal/edge span has no measured hard obstruction',max(span_errors)<1e-10)
summary={'commit':snapshot['commit'],'status':'passed_saved_data_and_equation_checks','assertions':len(checks),'checks':checks,'source_files':4,'source_groups':1,'verified_independent_upstream_groups':0,'patches':33,'observations':231,'support_vertex_observations':support_total,'normal_vertex_observations':normal_total,'normal_free_vertex_observations':nf_total,'label_replay_max_error_m':label_error,'feature_checks':feature_rows,'graph_checks':graph_rows,'overlaps':overlaps,'max_target_vector_span_residual':max(span_errors),'all_damage_centers_equal_patch_selection_centers':True,'cost':{'wall_s':time.perf_counter()-started,'cpu_s':time.process_time()-cpu,'formal_performance':False},'not_run':['author complete4130 assertion script','Blender exports','new damage generation','training or inference quality','contact/path acceptance','full cross-path pipeline regeneration']}
(HERE/'INDEPENDENT_RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({k:v for k,v in summary.items() if k not in ['checks','feature_checks','graph_checks','overlaps']}))
# Local feature arrays for the no-training representation check, excluded from Git.
target=HERE/'private'; target.mkdir(exist_ok=True)
axis=np.array([1.,2.,3.]); axis/=np.linalg.norm(axis); angle=.731
skew=np.array([[0.,-axis[2],axis[1]],[axis[2],0.,-axis[0]],[-axis[1],axis[0],0.]])
rotation=np.eye(3)*np.cos(angle)+(1-np.cos(angle))*np.outer(axis,axis)+np.sin(angle)*skew
for cid,p,t,ctx,g,features in feature_inputs:
    transformed=independent_features(2.3*(p@rotation.T)+np.array([1.3,-2.1,.7]),t,ctx,g)
    np.savez_compressed(target/(cid.replace('/','_')+'.npz'),**features,edge_index=g['edge_index'],free_mask=g['free_mask'],**{'transformed_'+k:v for k,v in transformed.items()})
