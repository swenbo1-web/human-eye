"""Independent arithmetic/descriptor review; never import the author's auditor."""
import os
for name in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[name] = '1'
import collections
import hashlib
import json
from pathlib import Path
import time
import numpy as np

HERE=Path(__file__).resolve().parent
SNAP=HERE/'snapshot'
AUTHOR=Path('C:/Users/Administrator/.codex/worktrees/m6-model-selection/hefe')
B=SNAP/'verification/m6_shape_observe_001'
D=SNAP/'verification/m6_shape_data_001'
T=SNAP/'verification/m6_shape_train_001'
O=SNAP/'verification/m6_shape_opt_001'
read=lambda p:json.loads(Path(p).read_bytes())
def npz(p):
    with np.load(p,allow_pickle=False) as z:return {k:z[k].copy() for k in z.files}
def local(p):return SNAP/Path(p).relative_to(AUTHOR)
CASES=sorted(read(D/'DATASET_INDEX.json')['cases']+[c for c in read(T/'PUBLIC_DATASET_INDEX.json')['cases'] if c['purpose']=='validation'],key=lambda c:c['id'])
LOOKUP={c['id']:c for c in CASES}
PREV={c['id']:c for g in ('development','validation') for c in read(O/'EVAL_FINAL_HARD.json')[g]['cases']}
STATS=npz(O/'private/normalization.npz')

def load(c):
    folder=(D/'private/patches' if c['purpose']=='development_train_pool' else T/'private/public_data/patches')/c['patch_id']
    sample=c['id'].split('/')[-1]
    i=npz(folder/'inputs'/(sample+'.npz'));g=npz(folder/'graph.npz');m=npz(folder/'mapping.npz')
    l=npz(folder/'labels'/(sample+'.npz'))
    obs=np.load(folder/'observed'/(sample+'.npy'),allow_pickle=False)
    ref=np.load(folder/'reference_local.npy',allow_pickle=False)
    comp=npz(local(PREV[c['id']]['component_path']))
    return dict(i=i,g=g,m=m,l=l,obs=obs,ref=ref,p=comp['p'],scale=float(i['scale_m']),folder=folder)

def forwards(s):
    node=s['i']['node_features'].copy()
    node[:,:5]=((node[:,:5].astype(float)-STATS['node_mean'])/STATS['node_std']).astype('float32')
    edge=((s['i']['edge_features'].astype(float)-STATS['edge_mean'])/STATS['edge_std']).astype('float32')
    return dict(node_features=node,edge_features=edge,positions=s['i']['positions'],normals=s['i']['normals'],edge_index=s['g']['edge_index'],free_mask=s['g']['free_mask'])

def distance(adj,seeds):
    d=np.full(len(adj),-1,dtype=int);queue=collections.deque(int(i) for i in seeds)
    for i in queue:d[i]=0
    while queue:
        i=queue.popleft()
        for j in adj[i]:
            if d[j]<0:d[j]=d[i]+1;queue.append(j)
    return d

def descriptors(s,ids):
    a,b=s['g']['edge_index'];n=len(s['obs'])
    adj=[[] for _ in range(n)];edges=[[] for _ in range(n)]
    for e,(i,j) in enumerate(zip(a,b)):adj[int(i)].append(int(j));edges[int(i)].append(e)
    q=s['i']['positions'].astype(float);normal=s['i']['normals'].astype(float)
    nf=s['i']['node_features'].astype(float);ef=s['i']['edge_features'].astype(float)
    rows=[];sizes=[]
    for i in ids:
        values=ef[edges[i]]
        base=np.r_[nf[i,:5],values.mean(0),np.sqrt(np.mean((values-values.mean(0))**2,axis=0))]
        hops=distance(adj,[i]);cs=[];vs=[];counts=[]
        for r in (2,4,8):
            use=(hops>0)&(hops<=r);delta=q[use]-q[i]
            cs.append(float(np.sum(delta*normal[i])/np.sum(delta**2)))
            vs.append(float(np.mean(1-np.clip(np.sum(normal[use]*normal[i],axis=1),-1,1))))
            counts.append(int(use.sum()))
        rows.append(np.r_[base,cs[0],cs[1]-cs[0],cs[2]-cs[1],vs[0],vs[1]-vs[0],vs[2]-vs[1]])
        sizes.append(counts)
    return np.asarray(rows),np.asarray(sizes),adj

checks=0;maxerr=collections.defaultdict(float)
def eq(a,b,tag):
    global checks
    checks+=1
    assert np.array_equal(a,b),tag
def close(a,b,tag,atol=2e-10):
    global checks
    checks+=1
    if a is None or b is None:assert a is None and b is None,tag;return
    x=np.asarray(a);y=np.asarray(b)
    err=float(np.max(np.abs(x-y))) if x.size else 0.
    maxerr[tag.split(':')[0]]=max(maxerr[tag.split(':')[0]],err)
    assert np.allclose(x,y,atol=atol,rtol=2e-12,equal_nan=False),(tag,err)

def metrics(y,score):
    y=np.asarray(y,dtype=bool);score=np.asarray(score,float)
    p,n=int(y.sum()),int((~y).sum())
    if not p or not n:return {'ROC_AUC':None,'AP':None,'positive':p,'negative':n,'points':len(y)}
    diff=score[y,None]-score[None,~y]
    auc=float(((diff>0)+.5*(diff==0)).mean())
    ap=0.
    for threshold in np.unique(score[y]):
        current=(score==threshold)&y;chosen=score>=threshold
        ap+=float(current.sum()/p*y[chosen].sum()/chosen.sum())
    return {'ROC_AUC':auc,'AP':ap,'positive':p,'negative':n,'points':len(y)}

def main():
    start,cpu=time.perf_counter(),time.process_time()
    arrays=npz(B/'RETRIEVAL_POINTS.npz');report=read(B/'RETRIEVAL_RESULTS.json')
    audit=read(B/'INPUT_AUDIT.json');arows={r['id']:r for r in audit['cases']}
    rows={r['id']:r for r in report['cases']}
    tau=read(O/'LOC_CALIBRATION.json')['tau']
    eq(arrays['case_ids'],[c['id'] for c in CASES],'case ordering')
    results={};groups={};refs={};totalS=0;maxhop=0;allhash=[];actualdesc=[]
    for ci,c in enumerate(CASES):
        s=load(c);a=arows[c['id']];r=rows[c['id']]
        support=s['l']['damaged_mask'];free=s['g']['free_mask'];target=(s['ref']-s['obs'])/s['scale'];mag=np.linalg.norm(target,axis=1)
        eq(target.astype('float32'),s['l']['target_normalized'],'target cast')
        eq(support,np.any(s['ref']!=s['obs'],axis=1),'support')
        if c['patch_id'] not in refs:
            refs[c['patch_id']]=load(LOOKUP[c['patch_id']+'/sample_00'])
        normal=refs[c['patch_id']]
        eq(s['ref'],normal['obs'],'pair normal')
        eq(int(support.sum()),a['denominators']['support'],'support denominator')
        totalS+=int(support.sum())
        close(np.sum(mag[support]**2),a['target_squared_sum'],'target energy')
        lo=0.
        for hi,b in zip((.02,.1,np.inf),a['bins']):
            use=support&(mag>lo)&(mag<=hi);miss=use&~(s['p'].astype(float)>tau)
            eq(int(use.sum()),b['points'],'bin count')
            eq(int(miss.sum()),b['tau_missed_points'],'bin misses')
            close(np.sum(mag[use]**2),b['target_squared_sum'],'bin energy')
            close(np.sum(mag[miss]**2),b['missed_target_squared_sum'],'bin missed energy')
            lo=hi
        eq(int(np.count_nonzero(support&np.any(s['i']['positions']!=normal['i']['positions'],axis=1))),a['support_positions_changed_float32_from_normal'],'changed float32 support')
        f=forwards(s);ids={}
        for name,v in f.items():
            ids[name]={'shape':list(v.shape),'dtype':str(v.dtype),'bytes':v.nbytes,'sha256':hashlib.sha256(v.tobytes()).hexdigest()}
            assert ids[name]==a['forward_inputs'][name],(c['id'],name)
        h=hashlib.sha256(json.dumps(ids,sort_keys=True).encode()).hexdigest();eq(h,a['combined_forward_identity'],'full input hash');allhash.append(h)
        freeids=np.flatnonzero(free);ordered=sorted(freeids,key=lambda v:int(s['m']['context_source_ids'][v]));m=min(64,len(ordered))
        selected=np.asarray([ordered[j*(len(ordered)-1)//(m-1)] for j in range(m)],dtype=int)
        use=np.flatnonzero(arrays['case_index']==ci)
        eq(selected,arrays['local_index'][use],'query selection')
        eq(s['m']['context_source_ids'][selected],arrays['source_vertex_id'][use],'source IDs')
        eq(support[selected],arrays['label'][use],'query labels')
        eq(s['p'][selected],arrays['frozen_p'][use],'query frozen score')
        close(mag[selected],arrays['target_norm'][use],'query magnitudes')
        d,sz,adj=descriptors(s,selected);actualdesc.append(d)
        close(d[:,:13],arrays['R0_description'][use],'R0 descriptor')
        close(d,arrays['R1_description'][use],'R1 descriptor')
        eq(sz,arrays['ball_sizes'][use],'neighborhood sizes')
        for name,seeds in [('to_label_normal',~support),('to_input_fixed',~free)]:
            hop=distance(adj,np.flatnonzero(seeds))[support]
            eq(int(np.count_nonzero(hop<0)),a['graph_distances'][name]['unreachable_support_points'],'unreachable')
            eq(int(np.count_nonzero(hop>12)),a['graph_distances'][name]['support_points_over_K12'],'K12')
            if len(hop):
                eq(int(hop.max()),a['graph_distances'][name]['reachable_hops']['maximum'],'hop maximum')
                if name=='to_input_fixed':maxhop=max(maxhop,int(hop.max()))
        cs={}
        for strength,sel in [('all_support',np.ones(m,bool)),('strong_support',~support[selected]|(mag[selected]>.1))]:
            cs[strength]={}
            for method,key in [('R0','R0_score'),('R1','R1_score'),('frozen_p','frozen_p')]:
                value=metrics(arrays['label'][use][sel],arrays[key][use][sel]);cs[strength][method]=value
                old=r['metrics']['common_valid'][strength][method]
                for k in value:close(value[k],old[k],'case metric:'+k)
        results[c['id']]=cs
        primary='development' if c['purpose']=='development_train_pool' else 'validation_'+c['position_group']
        names=[primary,'source_'+c['source']]
        if not c['normal_control']:names += [f"{primary}_r{c['radius_ratio']}_a{c['amplitude_ratio']}",f"{primary}_amplitude_{c['amplitude_ratio']}"]
        for name in names:groups.setdefault(name,[]).append(c)
    desc=np.concatenate(actualdesc)
    eq(len(set(allhash)),348,'unique full inputs')
    eq(sorted(groups),sorted(report['summaries']),'all groups')
    macros={}
    for name,cs in groups.items():
        macros[name]={}
        for strength in ('all_support','strong_support'):
            macros[name][strength]={}
            for method in ('R0','R1','frozen_p'):
                want=report['summaries'][name]['macro']['common_valid'][strength][method]
                metrics_out={}
                for key in ('ROC_AUC','AP'):
                    bypatch=collections.defaultdict(list)
                    for c in cs:
                        if c['normal_control']:continue
                        value=results[c['id']][strength][method][key]
                        if value is not None:bypatch[c['patch_id']].append(value)
                    value=float(np.mean([np.mean(v) for v in bypatch.values()])) if bypatch else None
                    close(value,want[key],'macro:'+key)
                    close(len(bypatch),want['valid_AUC_patches' if key=='ROC_AUC' else 'valid_AP_patches'],'macro denominator')
                    metrics_out[key]=value
                macros[name][strength][method]=metrics_out
    dev=np.asarray([CASES[i]['purpose']=='development_train_pool' for i in arrays['case_index']])
    member=np.asarray([CASES[i]['source'] for i in arrays['case_index']])
    pools={};replays=[]
    for method,dim in [('R0',13),('R1',19)]:
        vals=desc[:,:dim]
        for key,old in report['reference_pools'][method].items():
            eligible=dev.copy()
            if old['excluded_member'] is not None:eligible &= member!=old['excluded_member']
            ids=np.flatnonzero(eligible);mean=vals[ids].mean(0);std=np.maximum(vals[ids].std(0),1e-6)
            close(mean,old['mean'],'pool mean');close(std,old['std_used'],'pool std');eq(len(ids),old['valid_reference_points'],'pool count')
            eq(sorted(set(str(arrays['case_ids'][i]) for i in arrays['case_index'][ids])),old['reference_case_ids'],'pool cases')
            pools[(method,key)]=(ids,mean,std)
        neighbors=arrays[method+'_neighbor_rows']
        eq(np.all(dev[neighbors]),True,'neighbors development only')
        eq(np.all(member[neighbors[dev]]!=member[dev,None]),True,'no same member')
        eq(arrays['label'][neighbors],arrays[method+'_neighbor_labels'],'neighbor labels')
        eq(arrays['label'][neighbors].mean(1),arrays[method+'_score'],'five mean score')
        for ci,c in enumerate(CASES):
            qids=np.flatnonzero(arrays['case_index']==ci);key='all_development' if c['purpose']=='validation' else 'exclude_'+c['source']
            ids,mean,std=pools[(method,key)];nei=neighbors[qids]
            d=np.linalg.norm((vals[qids,None]-mean)/std-(vals[nei]-mean)/std,axis=2)
            close(d,arrays[method+'_neighbor_distances'][qids],'chosen distance')
        for qi in np.linspace(0,len(desc)-1,12,dtype=int):
            c=CASES[int(arrays['case_index'][qi])];key='all_development' if c['purpose']=='validation' else 'exclude_'+c['source']
            ids,mean,std=pools[(method,key)]
            dist=np.linalg.norm((vals[ids]-mean)/std-(vals[qi]-mean)/std,axis=1)
            order=np.lexsort((arrays['source_vertex_id'][ids],arrays['case_ids'][arrays['case_index'][ids]],dist))[:5]
            eq(ids[order],neighbors[qi],'exhaustive top five')
            replays.append({'method':method,'query_row':int(qi),'candidate_count':len(ids)})
    witness=read(B/'EVIDENCE_PLAN.json')['evidence'];wr=read(B/'WITNESS_RETRIEVAL.json')['evidence']
    for w,old in zip(witness,wr):
        c=LOOKUP[w['case_id']];s=load(c);di,_,_=descriptors(s,[w['local_index']])
        for method,dim in [('R0',13),('R1',19)]:
            key='all_development' if c['purpose']=='validation' else 'exclude_'+c['source'];ids,mean,std=pools[(method,key)]
            dist=np.linalg.norm((desc[ids,:dim]-mean)/std-(di[0,:dim]-mean)/std,axis=1)
            order=np.lexsort((arrays['source_vertex_id'][ids],arrays['case_ids'][arrays['case_index'][ids]],dist))[:5]
            eq(ids[order],[x['sampled_row'] for x in old['methods'][method]['neighbors']],'witness neighbors')
            close(dist[order],[x['distance'] for x in old['methods'][method]['neighbors']],'witness distances')
    out={'status':'passed','author_commit':'66e171ceb72c930ba534e1eb8317791d00bd2dba','assertions':checks,'observations':348,'support_points':totalS,'sampled_points':len(desc),'all_neighbor_records_checked':222720,'full_reference_top5_replays':replays,'witness_top5_replays':12,'groups_recomputed':len(groups),'max_support_hops_to_fixed':maxhop,'full_input_unique':len(set(allhash)),'primary_macro':{k:macros[k] for k in ('development','validation_center','validation_offcenter')},'max_numeric_errors':dict(maxerr),'frozen_model_calls':0,'new_training':0,'Bunny_arrays':0,'wall_s_before_final_write':time.perf_counter()-start,'CPU_s_before_final_write':time.process_time()-cpu}
    (HERE/'INDEPENDENT_RESULTS.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf8',newline='\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__':main()
