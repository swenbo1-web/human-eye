"""Independent equations and full saved-score review. Never imports author code."""
import os
for key in ('OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','OMP_NUM_THREADS'):os.environ[key]='1'
import json, time
from pathlib import Path
from collections import defaultdict, deque
import numpy as np

HERE=Path(__file__).resolve().parent
SNAP=HERE/'snapshot'
P=SNAP/'verification/m6_shape_ring_001'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
counts=defaultdict(int); maxdiff=defaultdict(float)
def local(path):return SNAP/Path(path).relative_to(AUTHOR)
def j(path):return json.loads(Path(path).read_bytes())
def npz(path):
    with np.load(path,allow_pickle=False) as a:return {k:a[k].copy() for k in a.files}
def ck(name,observed,expected,rtol=1e-8,atol=1e-11):
    counts[name]+=1
    if expected is None or observed is None:
        assert expected is None and observed is None,(name,observed,expected);return
    a,b=np.asarray(observed),np.asarray(expected)
    assert a.shape==b.shape,(name,a.shape,b.shape)
    if a.dtype.kind in 'biu' and b.dtype.kind in 'biu':assert np.array_equal(a,b),name
    else:
        assert np.allclose(a,b,rtol=rtol,atol=atol,equal_nan=True),(name,observed,expected)
        if a.size and np.any(np.isfinite(a-b)):maxdiff[name]=max(maxdiff[name],float(np.nanmax(np.abs(a-b))))
def rank(y,s):
    y=np.asarray(y,dtype=bool);s=np.asarray(s);n=len(y);pos=int(y.sum());neg=n-pos
    order=np.argsort(s,kind='stable');q=s[order];t=y[order]
    boundaries=np.r_[0,np.flatnonzero(np.diff(q)!=0)+1,n]
    p=np.add.reduceat(t.astype(np.int64),boundaries[:-1]);z=np.diff(boundaries)-p
    auc=float(np.sum(p*(np.cumsum(z)-z+z/2))/(pos*neg)) if pos and neg else None
    pd=p[::-1];zd=z[::-1]
    ap=float(np.sum(pd*np.cumsum(pd)/np.cumsum(pd+zd))/pos) if pos else None
    return {'points':n,'positive':pos,'negative':neg,'ROC_AUC':auc,'AP':ap}
def parts(mask,edges):
    adjacency=[[] for _ in mask]
    for a,b in edges.T:adjacency[int(a)].append(int(b));adjacency[int(b)].append(int(a))
    pending=set(np.flatnonzero(mask).tolist());out=[]
    while pending:
        seed=min(pending);pending.remove(seed);stack=[seed];component=[]
        while stack:
            v=stack.pop();component.append(v)
            for w in adjacency[v]:
                if w in pending:pending.remove(w);stack.append(w)
        out.append(np.array(sorted(component),dtype=np.int64))
    return out
def clusters(res,area,ell,edges,threshold):
    out=np.zeros(len(res));ids=np.zeros(len(res),dtype=np.int64);detail=[]
    for ordinal,members in enumerate(parts(np.abs(res)/ell>threshold,edges),1):
        ids[members]=ordinal
        signed=float(np.dot(area[members],res[members]));unsigned=float(np.dot(area[members],np.abs(res[members])))
        value=abs(signed)/(ell**3);keep=len(members)>=5
        if keep:out[members]=value
        detail.append({'vertices':len(members),'retained_at_least5':keep,'score_T':value,'energy_E':unsigned/ell**3,
                       'coherence_C':abs(signed)/unsigned if unsigned else 0,'area_native':float(area[members].sum())})
    return out,ids,detail
def fit(points):
    x,y,z=points.T;design=np.stack([x*x,x*y,y*y,x,y,np.ones(len(x))],axis=1)
    spatial=np.exp(-4*np.einsum('ij,ij->i',points,points));weights=spatial.copy();trace=[]
    for iteration in range(4):
        aw=design*np.sqrt(weights)[:,None];bw=z*np.sqrt(weights)
        # Explicit SVD solve independently of author's lstsq implementation.
        u,s,v=np.linalg.svd(aw,full_matrices=False)
        assert np.count_nonzero(s>s[0]*max(aw.shape)*np.finfo(float).eps)==6
        coefficient=v.T@((u.T@bw)/s);trace.append(s[0]/s[-1])
        if iteration<3:
            error=z-design@coefficient
            scale=max(1.4826*np.median(np.abs(error-np.median(error))),1e-4)
            t=error/(4.685*scale)
            weights=spatial*np.where(np.abs(t)<1,(1-t*t)**2,0)
    return coefficient,np.array(trace)
def breadth(adjacency,seed):
    distance={int(seed):0};queue=deque([int(seed)])
    while queue:
        v=queue.popleft()
        if distance[v]==10:continue
        for w in adjacency[v]:
            if w not in distance:distance[w]=distance[v]+1;queue.append(w)
    pairs=sorted((d,v) for v,d in distance.items() if d)
    return np.array([v for d,v in pairs]),np.array([d for d,v in pairs])
def operation(y,selected,area,ell,edges):
    tp=int((y&selected).sum());fp=int((~y&selected).sum());fn=int((y&~selected).sum());tn=int((~y&~selected).sum())
    pa=float(area[y].sum());tpa=float(area[y&selected].sum());fpa=float(area[~y&selected].sum());na=float(area[~y].sum())
    return {'points':len(y),'TP':tp,'FP':fp,'FN':fn,'TN':tn,
            'point_recall':tp/(tp+fn) if tp+fn else None,'point_precision':tp/(tp+fp) if tp+fp else None,
            'point_FPR':fp/(fp+tn) if fp+tn else None,'positive_area_native':pa,'selected_positive_area_native':tpa,
            'missed_positive_area_native':pa-tpa,'selected_normal_area_native':fpa,'normal_area_native':na,
            'area_recall':tpa/pa if pa else None,'area_precision':tpa/(tpa+fpa) if tpa+fpa else None,
            'zero_true_detection':tp==0 if tp+fn else None,'normal_case_any_selection':bool(tp+fp) if not y.any() else None,
            'selected_component_count':len(parts(selected,edges)),
            'selected_component_sizes':[len(c) for c in parts(selected,edges)]}
def main():
    started=time.perf_counter();cpu=time.process_time()
    white=j(P/'INPUT_WHITELIST.json');ev=j(P/'EVALUATION.json');cal=j(P/'CALIBRATION.json');resindex=j(P/'RESIDUALS.json')
    cases={r['id']:r for r in ev['cases']};rr={r['id']:r for r in resindex['cases']}
    olds={}
    for path in ('verification/m6_shape_data_001/DATASET_INDEX.json','verification/m6_shape_train_001/PUBLIC_DATASET_INDEX.json'):
        olds.update({r['id']:r for r in j(SNAP/path)['cases'] if r['purpose']!='reserved_test'})
    oldp=j(SNAP/'verification/m6_shape_opt_001/EVAL_FINAL_HARD.json')
    oldp={r['id']:r for g in ('development','validation') for r in oldp[g]['cases']}
    assert len(cases)==len(olds)==len(white['cases'])==348
    sources={};topologies={};adjacencies={};bfs_checked=set()
    for name,rec in white['sources'].items():
        source=npz(local(rec['path']));sources[name]=source;v=source['vertices'];faces=source['triangles']
        adjacency=[set() for _ in v]
        for a,b,c in faces:
            adjacency[a].update((int(b),int(c)));adjacency[b].update((int(a),int(c)));adjacency[c].update((int(a),int(b)))
        for i,row in enumerate(adjacency):row.discard(i)
        adjacencies[name]=adjacency
        cache=npz(P/'private/topology'/(name+'.npz'));topologies[name]=cache
        ck('source_CSR_counts',np.diff(cache['indptr']),[len(x) for x in adjacency])
        ck('source_CSR_indices',cache['indices'],[w for row in adjacency for w in sorted(row)])
    data={};selection_summary={}
    for w in white['cases']:
        identity=w['id'];row=cases[identity];old=olds[identity];res=npz(local(rr[identity]['path']));score=npz(local(row['score_path']))
        mapping=npz(local(w['mapping_path']));graph=npz(local(w['graph_path']));inp=npz(local(w['input']['path']))
        observed=np.load(local(w['observed']['path']),allow_pickle=False)
        original=sources[w['source']];current=original['vertices'].copy();context=mapping['context_source_ids'];current[context]=observed
        fi=np.flatnonzero(graph['free_mask']);fs=context[fi];n=len(fi);ell=float(inp['scale_m']);edge=res['free_edge_index']
        ck('mapping_context',res['context_source_ids'],context);ck('mapping_free_context',res['free_context_ids'],fi);ck('mapping_free_source',res['free_source_ids'],fs)
        ck('positions',res['query_positions'],current[fs]);ck('scale',res['ell'],ell)
        normals=inp['normals'][fi].astype(float);normals/=np.linalg.norm(normals,axis=1)[:,None]
        ck('normal',res['normal_unit'],normals)
        axes=np.eye(3)[np.argmin(np.abs(normals),axis=1)];t=np.cross(normals,axes);t/=np.linalg.norm(t,axis=1)[:,None]
        frames=np.stack([t,np.cross(normals,t),normals],axis=2);ck('frames',res['frame_basis'],frames)
        lookup={int(v):i for i,v in enumerate(fs)}
        fe=sorted((i,lookup[z]) for v,i in lookup.items() for z in adjacencies[w['source']][v] if z in lookup and i<lookup[z])
        ck('F_edges',edge,np.array(fe,dtype=np.int64).T)
        faces=original['triangles'];points=current[faces]
        facearea=np.linalg.norm(np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0]),axis=1)/2
        vertexarea=np.bincount(faces.ravel(),weights=np.repeat(facearea/3,3),minlength=len(current))
        ck('complete_incident_area',res['area'],vertexarea[fs])
        topo=topologies[w['source']];qr=np.searchsorted(topo['query_source_ids'],fs);ck('cache_rows',res['cache_query_rows'],qr)
        selected=sorted(set((0,n//2,n-1)))
        for pos in selected:
            q=int(fs[pos]);a,b=topo['neighbor_offsets'][qr[pos]:qr[pos]+2];ids=topo['neighbor_source_ids'][a:b];hops=topo['neighbor_hops'][a:b]
            key=(w['source'],q)
            if key not in bfs_checked:
                ni,nd=breadth(adjacencies[w['source']],q);ck('BFS_vertex',ids,ni);ck('BFS_hop',hops,nd);bfs_checked.add(key)
            vectors=current[ids]-current[q];radius=np.linalg.norm(vectors,axis=1).max();ck('query_R',res['R'][pos],radius)
            points=vectors@frames[pos]/radius
            for branch,mask in [('solid',np.ones(len(hops),bool)),('ring',hops>=6)]:
                coeff,cond=fit(points[mask]);ck('fit_coefficients',res[branch+'_coefficients'][pos],coeff)
                ck('fit_condition_trace',res[branch+'_condition_trace'][pos],cond)
                ck('fit_height',res[branch+'_r'][pos],coeff[5]*radius)
                ck('fit_point_count',res[branch+'_point_count'][pos],mask.sum())
        for branch in ('solid','ring'):
            ck('fit_available',res[branch+'_valid'],np.ones(n,bool));ck('fit_failure',res[branch+'_failure_code'],np.zeros(n,int))
        folder=local(w['observed']['path']).parents[1];reference=np.load(folder/'reference_local.npy',allow_pickle=False)
        y=npz(local(old['labels']['path']))['damaged_mask'][fi].astype(bool)
        target=reference[fi]-observed[fi];strong=np.linalg.norm(target,axis=1)>.1*ell;depth=np.sum(target*normals,axis=1)
        ck('support',score['support'],y);ck('strong',score['strong'],strong);ck('target_depth',score['target_depth'],depth)
        pk=npz(local(oldp[identity]['component_path']))['p'].reshape(-1)[fi].astype(float);ck('historical_p',score['old_p'],pk)
        current_scores={'old_p':pk}
        for branch in ('solid','ring'):
            signal=res[branch+'_r'];cs,ids,detail=clusters(signal,res['area'],ell,edge,cal['seed_thresholds'][branch])
            current_scores[branch+'_point']=np.abs(signal)/ell;current_scores[branch+'_cluster']=cs
            ck('component_ids',score[branch+'_component_ids'],ids)
            saved=row['configurations'][branch+'_cluster']['components'];ck('component_count',len(saved),len(detail))
            for actual,expected in zip(saved,detail):
                for k,value in expected.items():ck('component_'+k,actual[k],value)
            dr=row['depth'][branch]
            if y.any():
                baseline=float(np.sqrt(np.mean(depth[y]**2)));err=signal[y]-depth[y];rmse=float(np.sqrt(np.mean(err**2)))
                for k,val in {'support_RMSE_native':rmse,'zero_prediction_RMSE_native':baseline,'RMSE_ratio_to_zero':rmse/baseline,
                              'support_RMSE_over_ell':rmse/ell,'bias_native':float(err.mean()),'prediction_RMS_native':float(np.sqrt(np.mean(signal[y]**2)))}.items():ck('depth_'+k,dr[k],val)
            else:ck('normal_depth_none',dr['RMSE_ratio_to_zero'],None)
        for cfg,values in current_scores.items():
            ck('score_values',score[cfg],values)
            for task,label in [('support',y),('strong',strong)]:
                actual=rank(label,values)
                for k,val in actual.items():ck('ranking_'+k,row['configurations'][cfg]['rank'][task][k],val)
                if cfg!='old_p':
                    selected=values>cal['operating_thresholds'][cfg];ck('selected',score[cfg+'_selected'],selected)
                    result=operation(label,selected,res['area'],ell,edge)
                    for k,val in result.items():ck('operation_'+k,row['configurations'][cfg]['operation'][task][k],val)
        data[identity]={'res':res,'scores':current_scores,'support':y,'strong':strong}
    normals=[w['id'] for w in white['cases'] if w['normal_control'] and w['purpose']=='development_train_pool']
    ck('calibration_normal_count',len(normals),33)
    for branch in ('solid','ring'):
        pool=np.concatenate([data[i]['scores'][branch+'_point'] for i in normals])
        ck('calibration_point_count',len(pool),10405);ck('q90',cal['seed_thresholds'][branch],np.quantile(pool,.9))
    for cfg in ('solid_point','ring_point','solid_cluster','ring_cluster'):
        peaks=[float(data[i]['scores'][cfg].max()) for i in normals]
        ck('q95',cal['operating_thresholds'][cfg],np.quantile(peaks,.95))
        ck('normal_FP',len(cal['calibration_normal_false_patch_ids'][cfg]),sum(x>cal['operating_thresholds'][cfg] for x in peaks))
    group_results={}
    groups={
        'all':list(cases.values()),
        'development_center':[r for r in cases.values() if r['purpose']=='development_train_pool'],
        'validation_center':[r for r in cases.values() if r['purpose']=='validation' and r['position_group']=='center'],
        'validation_offcenter':[r for r in cases.values() if r['purpose']=='validation' and r['position_group']=='offcenter'],
        'development_normal_controls':[r for r in cases.values() if r['purpose']=='development_train_pool' and r['normal_control']],
        'validation_normal_controls':[r for r in cases.values() if r['purpose']=='validation' and r['normal_control']]}
    for name,rows in groups.items():
        sg=ev['groups'][name];summary={}
        for cfg in ('solid_point','ring_point','solid_cluster','ring_cluster','old_p'):
            result={}
            for task in ('support','strong'):
                ys=np.concatenate([data[r['id']][task] for r in rows]);ss=np.concatenate([data[r['id']]['scores'][cfg] for r in rows])
                pooled=rank(ys,ss)
                for k,val in pooled.items():ck('group_pool_'+k,sg['configurations'][cfg]['rank'][task]['point_pool'][k],val)
                macros={}
                for metric in ('ROC_AUC','AP'):
                    bypatch=defaultdict(list)
                    for r in rows:
                        val=rank(data[r['id']][task],data[r['id']]['scores'][cfg])[metric]
                        if val is not None:bypatch[r['patch_id']].append(val)
                    macro=float(np.mean([np.mean(x) for x in bypatch.values()])) if bypatch else None
                    ck('group_macro_'+metric,sg['configurations'][cfg]['rank'][task]['patch_macro_'+metric]['value'],macro);macros[metric]=macro
                result[task]={'pool':pooled,'patch_macro':macros}
            summary[cfg]=result
        for branch in ('solid','ring'):
            ratios=[r['depth'][branch]['RMSE_ratio_to_zero'] for r in rows if not r['normal_control']]
            if ratios:
                ck('group_depth_median',sg['depth'][branch]['RMSE_ratio_to_zero']['median'],np.median(ratios))
                summary[branch+'_depth_ratio_median']=float(np.median(ratios))
        group_results[name]=summary
    assert not ev['decision_gates']['depth_signal_goals_passed']
    assert not ev['decision_gates']['any_new_configuration_localization_goals_passed']
    diagnostics={}
    for name,rows in groups.items():
        if name not in ('development_normal_controls','validation_normal_controls','validation_center','validation_offcenter'):continue
        diagnostics[name]={}
        for branch in ('solid','ring'):
            pool=np.concatenate([data[r['id']]['scores'][branch+'_point'] for r in rows])
            diagnostics[name][branch]={'abs_residual_over_ell_quantiles':np.quantile(pool,[0,.5,.9,.95,.99,1]).tolist(),
              'seed_exceeding_points':int((pool>cal['seed_thresholds'][branch]).sum()),'points':len(pool),
              'retained_components':sum(sum(c['retained_at_least5'] for c in r['configurations'][branch+'_cluster']['components']) for r in rows)}
    out={'status':'passed','assertions':sum(counts.values()),'checks':dict(counts),'max_differences':dict(maxdiff),
         'coverage':{'sources':len(sources),'cases':len(cases),'F_point_observations':sum(len(d['support']) for d in data.values()),
                     'independently_rebuilt_BFS_queries':len(bfs_checked),'fit_queries':counts['fit_height'],
                     'all_case_configurations':len(cases)*5,'group_summaries':len(groups)},
         'group_results':group_results,'diagnostics_from_saved_scores':diagnostics,
         'wall_s':time.perf_counter()-started,'CPU_s':time.process_time()-cpu,
         'new_training':0,'new_repair':0,'new_neural_forward':0,'Bunny':0,
         'limits':['Fit replay first/middle/last F per case, not all218886 fits','Group ranking review six main groups; per-case metrics all cases','Current synthetic shape probe, no product or real-artist validation']}
    (HERE/'INDEPENDENT_RESULTS.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:out[k] for k in ('status','assertions','coverage','wall_s','CPU_s')}))
if __name__=='__main__':main()
